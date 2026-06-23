import requests
from typing import Dict, Any
from .config import API_BASE_URL

class EduAgentApiClient:
    def __init__(self, base_url: str = API_BASE_URL):
        self.base_url = base_url.rstrip("/")

    def create_task(self, user_input: str, mode: str, user_id: str, conversation_id: str = "", request_id: str = "", student_profile: Dict[str, Any] = None, history: list = None, requested_resources: list = None) -> Dict[str, Any]:
        url = f"{self.base_url}/api/chat/async"
        payload = {
            "user_input": user_input,
            "mode": mode,
            "user_id": user_id,
            "conversation_id": conversation_id,
            "request_id": request_id,
            "student_profile": student_profile or {},
            "history": history or [],
            "requested_resources": requested_resources or []
        }
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        return response.json()

    def get_task(self, task_id: str) -> Dict[str, Any]:
        url = f"{self.base_url}/api/task/{task_id}"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.json()

    def cancel_task(self, task_id: str) -> Dict[str, Any]:
        url = f"{self.base_url}/api/task/{task_id}/cancel"
        response = requests.post(url, timeout=10)
        response.raise_for_status()
        return response.json()

    def stream_task(self, task_id: str):
        url = f"{self.base_url}/api/task/{task_id}/stream"
        import json
        response = requests.get(url, stream=True, timeout=(10, 360))
        response.raise_for_status()
        for line in response.iter_lines():
            if line:
                decoded_line = line.decode("utf-8")
                if decoded_line.startswith("data: "):
                    data_str = decoded_line[6:]
                    yield json.loads(data_str)
    
    def check_health(self) -> bool:
        url = f"{self.base_url}/health"
        try:
            response = requests.get(url, timeout=5)
            return response.status_code == 200
        except:
            return False

class ApiClientError(Exception):
    pass

def raise_api_error(response):
    try:
        payload = response.json()
        message = payload.get("detail")
    except ValueError:
        message = response.text
    raise ApiClientError(message or f"HTTP {response.status_code}")

# --- Knowledge Base Extensions ---

def upload_document_api(api_client: EduAgentApiClient, file_path: str, user_id: str, course_id: str = None, scope: str = 'personal', conversation_id: str = None) -> Dict[str, Any]:
    import os
    url = f"{api_client.base_url}/api/knowledge/documents"
    with open(file_path, "rb") as file_obj:
        data = {
            "user_id": user_id,
            "scope": scope
        }
        if course_id:
            data["course_id"] = course_id
        if conversation_id:
            data["conversation_id"] = conversation_id
            
        response = requests.post(
            url,
            files={"file": (os.path.basename(file_path), file_obj)},
            data=data,
            timeout=(10, 120)
        )
    if response.status_code >= 400:
        raise_api_error(response)
    return response.json()

def get_documents_api(api_client: EduAgentApiClient, user_id: str = None, course_id: str = None, scope: str = None, status: str = None, page: int = 1, page_size: int = 100) -> Dict[str, Any]:
    url = f"{api_client.base_url}/api/knowledge/documents"
    params = {"page": page, "page_size": page_size}
    if user_id: params["user_id"] = user_id
    if course_id: params["course_id"] = course_id
    if scope: params["scope"] = scope
    if status: params["status"] = status
    
    response = requests.get(url, params=params, timeout=10)
    if response.status_code >= 400:
        raise_api_error(response)
    return response.json()

def get_document_api(api_client: EduAgentApiClient, document_id: str, user_id: str) -> Dict[str, Any]:
    url = f"{api_client.base_url}/api/knowledge/documents/{document_id}"
    response = requests.get(url, params={"user_id": user_id}, timeout=10)
    if response.status_code >= 400:
        raise_api_error(response)
    return response.json()

def delete_document_api(api_client: EduAgentApiClient, document_id: str, user_id: str) -> Dict[str, Any]:
    url = f"{api_client.base_url}/api/knowledge/documents/{document_id}"
    response = requests.delete(url, params={"user_id": user_id}, timeout=10)
    if response.status_code >= 400:
        raise_api_error(response)
    return response.json()

def reindex_document_api(api_client: EduAgentApiClient, document_id: str, user_id: str) -> Dict[str, Any]:
    url = f"{api_client.base_url}/api/knowledge/documents/{document_id}/reindex"
    response = requests.post(url, params={"user_id": user_id}, timeout=10)
    if response.status_code >= 400:
        raise_api_error(response)
    return response.json()

def get_index_task_status_api(api_client: EduAgentApiClient, index_task_id: str, user_id: str) -> Dict[str, Any]:
    url = f"{api_client.base_url}/api/knowledge/tasks/{index_task_id}"
    response = requests.get(url, params={"user_id": user_id}, timeout=10)
    if response.status_code >= 400:
        raise_api_error(response)
    return response.json()

# Bind methods to EduAgentApiClient dynamically to avoid large rewrite
EduAgentApiClient.upload_document = upload_document_api
EduAgentApiClient.get_documents = get_documents_api
EduAgentApiClient.get_document = get_document_api
EduAgentApiClient.delete_document = delete_document_api
EduAgentApiClient.reindex_document = reindex_document_api
EduAgentApiClient.get_index_task_status = get_index_task_status_api

