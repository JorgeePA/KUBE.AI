# 🤖 KUBEAI — Gestión de Kubernetes con Lenguaje Natural

KUBEAI es una herramienta de línea de comandos que permite gestionar un clúster de Kubernetes usando lenguaje natural en español, desarrollada como Trabajo de Fin de Máster.

---

## 📋 Descripción

El usuario escribe frases en español y KUBEAI las interpreta para ejecutar operaciones reales sobre Kubernetes: crear pods, deployments y servicios, escalarlos, listarlos, eliminarlos u obtener logs, todo sin necesidad de conocer la sintaxis de `kubectl`.

---

## 🧰 Requisitos previos

- Python 3.10 o superior
- [Minikube](https://minikube.sigs.k8s.io/) o cualquier clúster Kubernetes accesible
- [Ollama](https://ollama.com/) instalado y corriendo en local
- El modelo `mistral` descargado en Ollama

---

## ⚙️ Instalación

### 1. Clona el repositorio

```bash
git clone https://github.com/TU_USUARIO/kubeai.git
cd kubeai
```

### 2. Crea y activa el entorno virtual

```bash
python3 -m venv kubeai_env
source kubeai_env/bin/activate
```

### 3. Instala las dependencias

```bash
pip install -r requirements.txt
python -m spacy download es_core_news_md
```

### 4. Instala Ollama y descarga el modelo

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull mistral
```

### 5. Arranca Minikube

```bash
minikube start --driver=docker --memory=4096mb --cpus=2
# Si estás en una VM o como root:
minikube start --driver=none
```

---

## 🚀 Uso

```bash
python KUBEAI.py
```

### Ejemplos de comandos

| Lo que escribes | Lo que hace |
|---|---|
| `Crea un pod con nginx en el puerto 80` | Crea un Pod con imagen nginx |
| `Despliega 3 réplicas de redis` | Crea un Deployment con 3 réplicas |
| `Muéstrame los pods` | Lista todos los pods del namespace default |
| `Escala el deployment nginx-34821 a 5 réplicas` | Escala el deployment |
| `Elimina el pod nginx-34821` | Elimina el pod con confirmación previa |
| `Logs del pod nginx-34821` | Muestra los logs del pod |
| `ayuda` | Muestra el menú de comandos |

---

## 🏗️ Arquitectura

```
Entrada de usuario (texto en español)
        │
        ▼
   Ollama / Mistral  ←── LLM local, sin internet
        │
        ▼
  Comando estructurado (JSON)
        │
        ▼
  Cliente Kubernetes (kubernetes-python)
        │
        ▼
   Clúster Minikube
```

---

## 📁 Estructura del proyecto

```
kubeai_project/
├── KUBEAI.py             # Aplicación principal
├── app-deployment.yaml   # Ejemplo de deployment YAML
├── requirements.txt      # Dependencias Python
├── .gitignore            # Archivos excluidos del repositorio
└── README.md             # Este archivo
```

---

## 👨‍🎓 Autor

Proyecto de Fin de Máster — 2025
