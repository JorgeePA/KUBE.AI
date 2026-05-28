import spacy
import re
import random
from kubernetes import client, config
from kubernetes.client.rest import ApiException

# ─────────────────────────────────────────────
# Cargar el modelo en español de spaCy
# ─────────────────────────────────────────────
try:
    nlp = spacy.load("es_core_news_md")
except OSError:
    print("El modelo 'es_core_news_md' no está instalado. Descargándolo ahora...")
    spacy.cli.download("es_core_news_md")
    nlp = spacy.load("es_core_news_md")
except Exception as e:
    raise Exception(f"Error al cargar el modelo de spaCy: {e}")

# ─────────────────────────────────────────────
# Cargar configuración de Kubernetes
# ─────────────────────────────────────────────
try:
    config.load_kube_config()
except Exception as e:
    raise Exception(f"Error al cargar la configuración de Kubernetes: {e}")

v1 = client.CoreV1Api()
apps_v1 = client.AppsV1Api()

# ─────────────────────────────────────────────
# Diccionarios de sinónimos
# ─────────────────────────────────────────────

ACCIONES = {
    "create": ["crear", "crea", "hacer", "haz", "lanza", "lanzar", "desplegar",
               "despliega", "arranca", "arrancar", "iniciar", "inicia", "montar", "monta"],
    "delete": ["eliminar", "elimina", "borrar", "borra", "destruir", "destruye",
               "quitar", "quita", "remover", "remueve", "delete", "drop"],
    "scale":  ["escalar", "escala", "redimensionar", "ajustar", "aumentar",
               "reducir", "replica", "replicar", "scale"],
    "get":    ["obtener", "listar", "lista", "mostrar", "muestra", "ver", "enseña",
               "enseñar", "get", "consultar", "consulta", "dame", "dime"],
    "logs":   ["logs", "log", "registros", "registro", "trazas", "traza"],
}

RECURSOS = {
    "pod":        ["pod", "pods", "contenedor", "contenedores", "instancia", "instancias"],
    "deployment": ["deployment", "deployments", "despliegue", "despliegues",
                   "maquinas", "servidores", "aplicacion", "app"],
    "service":    ["service", "services", "servicio", "servicios", "svc"],
}

IMAGENES_CONOCIDAS = [
    "nginx", "apache", "httpd", "postgres", "postgresql", "mysql", "mariadb",
    "redis", "mongo", "mongodb", "rabbitmq", "kafka", "zookeeper", "elasticsearch",
    "kibana", "grafana", "prometheus", "node", "python", "ruby", "php", "java",
    "golang", "ubuntu", "alpine", "debian", "centos", "busybox", "traefik", "haproxy",
]

# ─────────────────────────────────────────────
# Utilidades
# ─────────────────────────────────────────────

def generar_nombre_recurso(base_name):
    clean = re.sub(r"[^a-z0-9\-]", "", base_name.lower().replace(" ", "-"))
    return f"{clean}-{random.randint(10000, 99999)}"


def detectar_accion(frase):
    frase_lower = frase.lower()
    for accion, palabras in ACCIONES.items():
        for p in palabras:
            if re.search(rf"\b{re.escape(p)}\b", frase_lower):
                return accion
    return None


def detectar_recurso(frase):
    frase_lower = frase.lower()
    for recurso, palabras in RECURSOS.items():
        for p in palabras:
            if re.search(rf"\b{re.escape(p)}\b", frase_lower):
                return recurso
    return None


def detectar_imagen(frase):
    frase_lower = frase.lower()
    for img in IMAGENES_CONOCIDAS:
        if re.search(rf"\b{re.escape(img)}\b", frase_lower):
            tag_match = re.search(rf"\b({re.escape(img)}:[a-z0-9._\-]+)\b", frase_lower)
            return tag_match.group(1) if tag_match else img
    tag_match = re.search(r"\b([a-z0-9_.\-]+:[a-z0-9._\-]+)\b", frase_lower)
    if tag_match:
        return tag_match.group(1)
    user_img_match = re.search(r"\b([a-z0-9_.\-]+/[a-z0-9._\-]+)\b", frase_lower)
    if user_img_match:
        return user_img_match.group(1)
    return None


def detectar_replicas(doc):
    numeros_texto = {
        "un": 1, "uno": 1, "una": 1, "dos": 2, "tres": 3, "cuatro": 4,
        "cinco": 5, "seis": 6, "siete": 7, "ocho": 8, "nueve": 9, "diez": 10,
    }
    for token in doc:
        if token.pos_ == "NUM":
            try:
                return int(token.text)
            except ValueError:
                pass
        if token.text.lower() in numeros_texto:
            return numeros_texto[token.text.lower()]
    return 1


def detectar_puerto(frase):
    match = re.search(r"puerto\s+(\d+)", frase, re.IGNORECASE)
    if match:
        return int(match.group(1))
    match2 = re.search(r"port\s+(\d+)", frase, re.IGNORECASE)
    if match2:
        return int(match2.group(1))
    return None


def detectar_nombre_recurso_existente(frase):
    match = re.search(r"\b([a-z0-9]+-\d{5})\b", frase.lower())
    if match:
        return match.group(1)
    return None


def confirmar_operacion(mensaje):
    print(f"\n⚠️  ATENCION: {mensaje}")
    respuesta = input("Estas seguro? Escribe 'si' para confirmar o cualquier otra cosa para cancelar: ").strip().lower()
    return respuesta in ["si", "s", "yes", "y"]


def listar_recursos(recurso):
    try:
        if recurso == "pod":
            items = v1.list_namespaced_pod(namespace="default").items
            return [p.metadata.name for p in items]
        elif recurso == "deployment":
            items = apps_v1.list_namespaced_deployment(namespace="default").items
            return [d.metadata.name for d in items]
        elif recurso == "service":
            items = v1.list_namespaced_service(namespace="default").items
            return [s.metadata.name for s in items]
    except Exception:
        return []
    return []


# ─────────────────────────────────────────────
# Núcleo: interpretar y ejecutar comandos
# ─────────────────────────────────────────────

def interpretar_comando(frase):
    doc = nlp(frase.lower())

    accion   = detectar_accion(frase)
    recurso  = detectar_recurso(frase)
    imagen   = detectar_imagen(frase)
    replicas = detectar_replicas(doc)
    puerto   = detectar_puerto(frase)
    nombre   = detectar_nombre_recurso_existente(frase)

    if not nombre:
        nombre = generar_nombre_recurso(imagen or recurso or "resource")

    # ── Validación ────────────────────────────────────────────────────────
    if not accion:
        return (
            "No entendi la accion que quieres realizar.\n"
            "Puedes usar: crear, eliminar, escalar, listar, logs.\n"
            "Ejemplo: 'Crea un pod con nginx en el puerto 80'"
        )

    if not recurso:
        return (
            "No entendi el tipo de recurso.\n"
            "Recursos disponibles: pod, deployment, service.\n"
            "Ejemplo: 'Crea un deployment con 3 replicas de nginx'"
        )

    # ── Ejecución ─────────────────────────────────────────────────────────
    try:

        # CREATE
        if accion == "create":

            if recurso == "pod":
                pod = client.V1Pod(
                    metadata=client.V1ObjectMeta(name=nombre),
                    spec=client.V1PodSpec(
                        containers=[client.V1Container(
                            name=nombre,
                            image=imagen or "nginx",
                            ports=[client.V1ContainerPort(container_port=puerto)] if puerto else []
                        )]
                    )
                )
                v1.create_namespaced_pod(namespace="default", body=pod)
                return (
                    f"Pod '{nombre}' creado con imagen '{imagen or 'nginx'}'"
                    + (f" en el puerto {puerto}." if puerto else ".")
                )

            elif recurso == "deployment":
                deployment = client.V1Deployment(
                    metadata=client.V1ObjectMeta(name=nombre),
                    spec=client.V1DeploymentSpec(
                        replicas=replicas,
                        selector=client.V1LabelSelector(match_labels={"app": nombre}),
                        template=client.V1PodTemplateSpec(
                            metadata=client.V1ObjectMeta(labels={"app": nombre}),
                            spec=client.V1PodSpec(
                                containers=[client.V1Container(
                                    name=nombre,
                                    image=imagen or "nginx",
                                    ports=[client.V1ContainerPort(container_port=puerto)] if puerto else []
                                )]
                            )
                        )
                    )
                )
                apps_v1.create_namespaced_deployment(namespace="default", body=deployment)
                return (
                    f"Deployment '{nombre}' creado con {replicas} replica(s) de '{imagen or 'nginx'}'"
                    + (f" en el puerto {puerto}." if puerto else ".")
                )

            elif recurso == "service":
                service = client.V1Service(
                    metadata=client.V1ObjectMeta(name=nombre),
                    spec=client.V1ServiceSpec(
                        selector={"app": nombre},
                        ports=[client.V1ServicePort(port=puerto or 80, target_port=puerto or 80)],
                        type="ClusterIP"
                    )
                )
                v1.create_namespaced_service(namespace="default", body=service)
                return f"Servicio '{nombre}' creado en el puerto {puerto or 80}."

        # DELETE
        elif accion == "delete":
            nombre_explicito = detectar_nombre_recurso_existente(frase)
            if not nombre_explicito:
                disponibles = listar_recursos(recurso)
                if not disponibles:
                    return f"No hay {recurso}s en el namespace 'default' para eliminar."
                lista = "\n  - ".join(disponibles)
                return (
                    f"No especificaste el nombre exacto del {recurso} a eliminar.\n"
                    f"{recurso}s disponibles:\n  - {lista}\n\n"
                    f"Ejemplo: 'elimina el {recurso} {disponibles[0]}'"
                )

            if not confirmar_operacion(f"Vas a eliminar el {recurso} '{nombre_explicito}'."):
                return "Operacion cancelada."

            if recurso == "pod":
                v1.delete_namespaced_pod(name=nombre_explicito, namespace="default")
                return f"Pod '{nombre_explicito}' eliminado."
            elif recurso == "deployment":
                apps_v1.delete_namespaced_deployment(name=nombre_explicito, namespace="default")
                return f"Deployment '{nombre_explicito}' eliminado."
            elif recurso == "service":
                v1.delete_namespaced_service(name=nombre_explicito, namespace="default")
                return f"Servicio '{nombre_explicito}' eliminado."

        # SCALE
        elif accion == "scale":
            if recurso != "deployment":
                return "Solo se puede escalar deployments."

            nombre_explicito = detectar_nombre_recurso_existente(frase)
            if not nombre_explicito:
                disponibles = listar_recursos("deployment")
                if not disponibles:
                    return "No hay deployments disponibles para escalar."
                lista = "\n  - ".join(disponibles)
                return (
                    f"No especificaste el nombre del deployment.\n"
                    f"Deployments disponibles:\n  - {lista}\n\n"
                    f"Ejemplo: 'escala el deployment {disponibles[0]} a 3 replicas'"
                )

            apps_v1.patch_namespaced_deployment_scale(
                name=nombre_explicito,
                namespace="default",
                body={"spec": {"replicas": replicas}}
            )
            return f"Deployment '{nombre_explicito}' escalado a {replicas} replica(s)."

        # GET
        elif accion == "get":
            if recurso == "pod":
                pods = v1.list_namespaced_pod(namespace="default").items
                if not pods:
                    return "No hay pods en el namespace 'default'."
                return "Pods:\n" + "\n".join(
                    f"  - {p.metadata.name}  [{p.status.phase}]" for p in pods
                )
            elif recurso == "deployment":
                deps = apps_v1.list_namespaced_deployment(namespace="default").items
                if not deps:
                    return "No hay deployments en el namespace 'default'."
                return "Deployments:\n" + "\n".join(
                    f"  - {d.metadata.name}  (replicas: {d.spec.replicas})" for d in deps
                )
            elif recurso == "service":
                svcs = v1.list_namespaced_service(namespace="default").items
                if not svcs:
                    return "No hay services en el namespace 'default'."
                return "Services:\n" + "\n".join(
                    f"  - {s.metadata.name}  [{s.spec.type}]" for s in svcs
                )

        # LOGS
        elif accion == "logs":
            if recurso != "pod":
                return "Solo se pueden obtener logs de pods."

            nombre_explicito = detectar_nombre_recurso_existente(frase)
            if not nombre_explicito:
                disponibles = listar_recursos("pod")
                if not disponibles:
                    return "No hay pods disponibles."
                lista = "\n  - ".join(disponibles)
                return (
                    f"No especificaste el nombre del pod.\n"
                    f"Pods disponibles:\n  - {lista}\n\n"
                    f"Ejemplo: 'logs del pod {disponibles[0]}'"
                )

            logs = v1.read_namespaced_pod_log(name=nombre_explicito, namespace="default")
            return f"Logs de '{nombre_explicito}':\n{logs}"

    except ApiException as e:
        return f"Error de Kubernetes: {e.reason} (codigo {e.status})"
    except Exception as e:
        return f"Error inesperado: {str(e)}"

    return "No se pudo ejecutar la operacion."


# ─────────────────────────────────────────────
# Ayuda
# ─────────────────────────────────────────────

AYUDA = """
╔══════════════════════════════════════════════════════════╗
║              KUBEAI — Comandos disponibles               ║
╠══════════════════════════════════════════════════════════╣
║  CREAR                                                   ║
║  · "Crea un pod con nginx en el puerto 80"               ║
║  · "Crea un deployment con 3 replicas de redis"          ║
║  · "Lanza un servicio en el puerto 8080"                 ║
║  · "Despliega una app con imagen bitnami/wordpress"      ║
║                                                          ║
║  LISTAR                                                  ║
║  · "Muestrame los pods"                                  ║
║  · "Lista los deployments"                               ║
║  · "Dame los servicios"                                  ║
║                                                          ║
║  ESCALAR                                                 ║
║  · "Escala el deployment nginx-34821 a 5 replicas"       ║
║                                                          ║
║  ELIMINAR                                                ║
║  · "Elimina el pod nginx-34821"                          ║
║  · "Borra el deployment redis-12345"                     ║
║                                                          ║
║  LOGS                                                    ║
║  · "Muestrame los logs del pod nginx-34821"              ║
║                                                          ║
║  Escribe 'ayuda' para ver este menu.                     ║
║  Escribe 'salir' para terminar.                          ║
╚══════════════════════════════════════════════════════════╝
"""


# ─────────────────────────────────────────────
# Bucle principal
# ─────────────────────────────────────────────

def interactuar_con_usuario():
    print(AYUDA)
    while True:
        try:
            frase_usuario = input("\nKUBEAI > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nSaliendo de KUBEAI.")
            break

        if not frase_usuario:
            continue

        if frase_usuario.lower() == "salir":
            print("Hasta luego.")
            break

        if frase_usuario.lower() in ["ayuda", "help", "?"]:
            print(AYUDA)
            continue

        resultado = interpretar_comando(frase_usuario)
        print(f"\n{resultado}\n")


if __name__ == "__main__":
    interactuar_con_usuario()
