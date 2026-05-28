import spacy
import re
import uuid
import random
from kubernetes import client, config
from kubernetes.client.rest import ApiException
from transformers import pipeline
from datetime import datetime

# Cargar el modelo en español de spaCy
try:
    nlp = spacy.load("es_core_news_md")
except OSError:
    print("El modelo 'es_core_news_md' no está instalado. Descargándolo ahora...")
    spacy.cli.download("es_core_news_md")
    nlp = spacy.load("es_core_news_md")
except Exception as e:
    raise Exception(f"Error al cargar el modelo de spaCy: {e}")

# Cargar el modelo de Hugging Face para respuestas naturales
generator = pipeline("text-generation", model="datificate/gpt2-small-spanish")

# Cargar la configuración de Kubernetes
try:
    config.load_kube_config()
except Exception as e:
    raise Exception(f"Error al cargar la configuración de Kubernetes: {e}")

v1 = client.CoreV1Api()
apps_v1 = client.AppsV1Api()

# Función para generar un nombre único para recursos
def generar_nombre_recurso(base_name):
    return f"{base_name}-{random.randint(10000, 99999)}"

# Función para interpretar y ejecutar comandos en Kubernetes
def interpretar_comando(frase):
    doc = nlp(frase.lower())
    comando = {"action": None, "resource": None, "name": None, "image": None, "replicas": 1, "port": None}
    response = ""

    # Detectar acción
    if any(word in frase for word in ["crear", "hacer", "crea"]):
        comando["action"] = "create"
    elif any(word in frase for word in ["eliminar", "borrar", "delete"]):
        comando["action"] = "delete"
    elif any(word in frase for word in ["escalar", "escala", "scale"]):
        comando["action"] = "scale"
    elif any(word in frase for word in ["obtener", "listar", "get"]):
        comando["action"] = "get"
    elif "logs" in frase:
        comando["action"] = "logs"

    # Detectar tipo de recurso
    if any(word in frase for word in ["pod", "contenedor"]):
        comando["resource"] = "pod"
    elif any(word in frase for word in ["deployment", "máquinas", "instancias", "servidores"]):
        comando["resource"] = "deployment"
    elif "service" in frase or "servicio" in frase:
        comando["resource"] = "service"

    # Detectar número de réplicas
    for token in doc:
        if token.pos_ == "NUM":
            try:
                comando["replicas"] = int(token.text)
            except ValueError:
                pass

    # Detectar imagen
    for token in doc:
        if token.text in ["nginx", "postgres", "mysql", "redis"]:
            comando["image"] = token.text

    # Detectar puerto
    port_match = re.search(r"puerto\s+(\d+)", frase)
    if port_match:
        comando["port"] = int(port_match.group(1))

    # Detectar nombre del recurso
    for ent in doc.ents:
        if ent.label_ in ["ORG", "PRODUCT"]:
            comando["name"] = ent.text.lower().replace(" ", "-")
    if not comando["name"]:
        comando["name"] = generar_nombre_recurso(comando["image"] or comando["resource"] or "resource")

    # Validar comando
    if not comando["action"] or not comando["resource"]:
        generated = generator(f"Interpreta esta solicitud de Kubernetes: {frase}", max_length=50, num_return_sequences=1)
        return f"No entendí la solicitud. Sugerencia: {generated[0]['generated_text']}. Por favor, sé más específico."

    # Ejecutar el comando según la acción
    try:
        if comando["action"] == "create":
            if comando["resource"] == "pod":
                pod = client.V1Pod(
                    metadata=client.V1ObjectMeta(name=comando["name"]),
                    spec=client.V1PodSpec(
                        containers=[client.V1Container(
                            name=comando["name"],
                            image=comando["image"] or "nginx",
                            ports=[client.V1ContainerPort(container_port=comando["port"])] if comando["port"] else []
                        )]
                    )
                )
                v1.create_namespaced_pod(namespace="default", body=pod)
                response = f"Pod {comando['name']} creado con imagen {comando['image'] or 'nginx'}."
            
            elif comando["resource"] == "deployment":
                deployment = client.V1Deployment(
                    metadata=client.V1ObjectMeta(name=comando["name"]),
                    spec=client.V1DeploymentSpec(
                        replicas=comando["replicas"],
                        selector=client.V1LabelSelector(match_labels={"app": comando["name"]}),
                        template=client.V1PodTemplateSpec(
                            metadata=client.V1ObjectMeta(labels={"app": comando["name"]}),
                            spec=client.V1PodSpec(
                                containers=[client.V1Container(
                                    name=comando["name"],
                                    image=comando["image"] or "nginx",
                                    ports=[client.V1ContainerPort(container_port=comando["port"])] if comando["port"] else []
                                )]
                            )
                        )
                    )
                )
                apps_v1.create_namespaced_deployment(namespace="default", body=deployment)
                response = f"Deployment {comando['name']} creado con {comando['replicas']} réplicas de {comando['image'] or 'nginx'}."
            
            elif comando["resource"] == "service":
                if not comando["image"]:
                    return "Debe especificar un deployment para exponer como servicio."
                service = client.V1Service(
                    metadata=client.V1ObjectMeta(name=comando["name"]),
                    spec=client.V1ServiceSpec(
                        selector={"app": comando["name"]},
                        ports=[client.V1ServicePort(port=comando["port"] or 80, target_port=comando["port"] or 80)],
                        type="ClusterIP"
                    )
                )
                v1.create_namespaced_service(namespace="default", body=service)
                response = f"Servicio {comando['name']} creado en el puerto {comando['port'] or 80}."

        elif comando["action"] == "delete":
            if comando["resource"] == "pod":
                v1.delete_namespaced_pod(name=comando["name"], namespace="default")
                response = f"Pod {comando['name']} eliminado."
            elif comando["resource"] == "deployment":
                apps_v1.delete_namespaced_deployment(name=comando["name"], namespace="default")
                response = f"Deployment {comando['name']} eliminado."
            elif comando["resource"] == "service":
                v1.delete_namespaced_service(name=comando["name"], namespace="default")
                response = f"Servicio {comando['name']} eliminado."

        elif comando["action"] == "scale":
            if comando["resource"] == "deployment":
                apps_v1.patch_namespaced_deployment_scale(
                    name=comando["name"],
                    namespace="default",
                    body={"spec": {"replicas": comando["replicas"]}}
                )
                response = f"Deployment {comando['name']} escalado a {comando['replicas']} réplicas."
            else:
                return "Solo se puede escalar deployments."

        elif comando["action"] == "get":
            if comando["resource"] == "pod":
                pods = v1.list_namespaced_pod(namespace="default")
                response = "\n".join([f"Pod: {pod.metadata.name}" for pod in pods.items])
            elif comando["resource"] == "deployment":
                deployments = apps_v1.list_namespaced_deployment(namespace="default")
                response = "\n".join([f"Deployment: {dep.metadata.name}" for dep in deployments.items])
            elif comando["resource"] == "service":
                services = v1.list_namespaced_service(namespace="default")
                response = "\n".join([f"Servicio: {svc.metadata.name}" for svc in services.items])

        elif comando["action"] == "logs":
            if comando["resource"] == "pod":
                logs = v1.read_namespaced_pod_log(name=comando["name"], namespace="default")
                response = f"Logs de {comando['name']}:\n{logs}"
            else:
                return "Solo se pueden obtener logs de pods."

    except ApiException as e:
        return f"Error al ejecutar la operación en Kubernetes: {e.reason} ({e.status})"
    except Exception as e:
        return f"Error inesperado: {str(e)}"

    return response

# Función para interactuar con el usuario
def interactuar_con_usuario():
    print("Bienvenido a KUBEAI: Herramienta de gestión de Kubernetes con IA")
    while True:
        frase_usuario = input("¿Qué deseas hacer en Kubernetes? (Escribe 'salir' para terminar): ")
        if frase_usuario.lower() == "salir":
            print("Saliendo de la herramienta.")
            break
        resultado = interpretar_comando(frase_usuario)
        print(resultado)

# Iniciar la interacción
if __name__ == "__main__":
    interactuar_con_usuario()