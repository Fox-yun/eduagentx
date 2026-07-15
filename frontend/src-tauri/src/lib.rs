use std::{
    collections::HashMap,
    io::Cursor,
    path::{Path, PathBuf},
    sync::Arc,
    time::Duration,
};

use base64::{engine::general_purpose::STANDARD as BASE64, Engine as _};
use directories::{ProjectDirs, UserDirs};
use futures_util::StreamExt;
use keyring::Entry;
use regex::Regex;
use reqwest::{header::HeaderMap, Client, Method, Url};
use reqwest_cookie_store::{CookieStore, CookieStoreMutex};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use tauri::{AppHandle, Manager, State};
use tauri_plugin_notification::NotificationExt;
use tokio::{fs, io::AsyncWriteExt, sync::Mutex};

/// Maximum cache size in bytes (5 GB)
const MAX_CACHE_SIZE_BYTES: u64 = 5 * 1024 * 1024 * 1024;
/// Maximum age for .part files in seconds (1 hour)
const PART_FILE_MAX_AGE_SECONDS: u64 = 3600;

const KEYRING_SERVICE: &str = "com.eduagentx.desktop";
const KEYRING_ACCOUNT: &str = "session-cookies";
const DEFAULT_TIMEOUT_SECONDS: u64 = 30;

/// File extensions that are safe to open with the system default application.
const ALLOWED_FILE_EXTENSIONS: &[&str] = &[
    ".pdf", ".pptx", ".docx", ".zip", ".mp4", ".png", ".jpg", ".jpeg", ".txt",
    ".webp", ".gif", ".svg", ".csv", ".json", ".md",
];

/// File extensions that are explicitly dangerous and must never be opened.
const BLOCKED_FILE_EXTENSIONS: &[&str] = &[
    ".exe", ".com", ".bat", ".cmd", ".ps1", ".vbs", ".js", ".msi", ".lnk",
    ".scr", ".sh", ".dll", ".wsf", ".hta",
];

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
struct DesktopConfigFile {
    server_url: Option<String>,
    download_dir: Option<String>,
    remember_session: bool,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct DesktopConfigResponse {
    server_url: Option<String>,
    download_dir: String,
    remember_session: bool,
    configured: bool,
    version: String,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct DesktopError {
    code: String,
    message: String,
    status: Option<u16>,
}

impl DesktopError {
    fn new(code: impl Into<String>, message: impl Into<String>) -> Self {
        Self {
            code: code.into(),
            message: message.into(),
            status: None,
        }
    }

    fn status(code: impl Into<String>, message: impl Into<String>, status: u16) -> Self {
        Self {
            code: code.into(),
            message: message.into(),
            status: Some(status),
        }
    }
}

impl std::fmt::Display for DesktopError {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(formatter, "{}", self.message)
    }
}

impl std::error::Error for DesktopError {}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
struct NativeMultipartPart {
    name: String,
    value: Option<String>,
    filename: Option<String>,
    content_type: Option<String>,
    bytes_base64: Option<String>,
    file_path: Option<String>,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
struct NativeApiRequest {
    path: String,
    method: String,
    headers: HashMap<String, String>,
    body: Option<String>,
    multipart: Option<Vec<NativeMultipartPart>>,
    timeout_ms: Option<u64>,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct NativeApiResponse {
    status: u16,
    headers: HashMap<String, String>,
    body: String,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct DownloadResult {
    path: String,
    filename: String,
}

struct DesktopInner {
    config: DesktopConfigFile,
    cookies: Arc<CookieStoreMutex>,
    client: Client,
}

struct DesktopState {
    inner: Mutex<DesktopInner>,
    config_path: PathBuf,
    cache_dir: PathBuf,
}

impl DesktopState {
    fn load() -> Result<Self, DesktopError> {
        let project_dirs = ProjectDirs::from("com", "EduAgentX", "EduAgentX")
            .ok_or_else(|| DesktopError::new("CONFIG_DIR_UNAVAILABLE", "无法确定客户端配置目录"))?;
        let config_dir = project_dirs.config_dir().to_path_buf();
        let cache_dir = project_dirs.cache_dir().to_path_buf();
        std::fs::create_dir_all(&config_dir)
            .map_err(|error| DesktopError::new("CONFIG_WRITE_FAILED", error.to_string()))?;
        std::fs::create_dir_all(&cache_dir)
            .map_err(|error| DesktopError::new("CACHE_WRITE_FAILED", error.to_string()))?;

        let config_path = config_dir.join("desktop.json");
        let config: DesktopConfigFile = std::fs::read_to_string(&config_path)
            .ok()
            .and_then(|value| serde_json::from_str(&value).ok())
            .unwrap_or_default();
        let cookies = Arc::new(CookieStoreMutex::new(load_persisted_cookies(
            config.remember_session,
        )));
        let client = build_client(Arc::clone(&cookies))?;
        Ok(Self {
            inner: Mutex::new(DesktopInner {
                config,
                cookies,
                client,
            }),
            config_path,
            cache_dir,
        })
    }
}

fn build_client(cookies: Arc<CookieStoreMutex>) -> Result<Client, DesktopError> {
    Client::builder()
        .cookie_provider(cookies)
        .user_agent(format!(
            "EduAgentX-Desktop/{} Windows-x64",
            env!("CARGO_PKG_VERSION")
        ))
        .connect_timeout(Duration::from_secs(12))
        .build()
        .map_err(|error| DesktopError::new("HTTP_CLIENT_FAILED", error.to_string()))
}

fn load_persisted_cookies(enabled: bool) -> CookieStore {
    if !enabled {
        return CookieStore::default();
    }
    let Ok(entry) = Entry::new(KEYRING_SERVICE, KEYRING_ACCOUNT) else {
        return CookieStore::default();
    };
    let Ok(encoded) = entry.get_password() else {
        return CookieStore::default();
    };
    let Ok(bytes) = BASE64.decode(encoded) else {
        return CookieStore::default();
    };
    CookieStore::load_json(Cursor::new(bytes)).unwrap_or_default()
}

fn save_persisted_cookies(cookies: &CookieStoreMutex) -> Result<(), DesktopError> {
    let store = cookies
        .lock()
        .map_err(|_| DesktopError::new("SESSION_LOCK_FAILED", "登录会话暂时不可用"))?;
    let mut bytes = Vec::new();
    store
        .save_json(&mut bytes)
        .map_err(|error| DesktopError::new("SESSION_SERIALIZE_FAILED", error.to_string()))?;
    let entry = Entry::new(KEYRING_SERVICE, KEYRING_ACCOUNT)
        .map_err(|error| DesktopError::new("SESSION_STORE_FAILED", error.to_string()))?;
    entry
        .set_password(&BASE64.encode(bytes))
        .map_err(|error| DesktopError::new("SESSION_STORE_FAILED", error.to_string()))
}

fn delete_persisted_cookies() {
    if let Ok(entry) = Entry::new(KEYRING_SERVICE, KEYRING_ACCOUNT) {
        let _ = entry.delete_credential();
    }
}

fn default_download_dir() -> PathBuf {
    UserDirs::new()
        .and_then(|dirs| dirs.download_dir().map(Path::to_path_buf))
        .unwrap_or_else(|| std::env::current_dir().unwrap_or_else(|_| PathBuf::from(".")))
}

fn write_config(path: &Path, config: &DesktopConfigFile) -> Result<(), DesktopError> {
    let value = serde_json::to_vec_pretty(config)
        .map_err(|error| DesktopError::new("CONFIG_SERIALIZE_FAILED", error.to_string()))?;
    std::fs::write(path, value)
        .map_err(|error| DesktopError::new("CONFIG_WRITE_FAILED", error.to_string()))
}

fn validate_server_url(raw: &str) -> Result<String, DesktopError> {
    let trimmed = raw.trim().trim_end_matches('/');
    let url = Url::parse(trimmed).map_err(|_| {
        DesktopError::new(
            "INVALID_SERVER_URL",
            "请输入完整的服务地址，例如 https://api.example.com",
        )
    })?;
    if !url.username().is_empty()
        || url.password().is_some()
        || url.query().is_some()
        || url.fragment().is_some()
    {
        return Err(DesktopError::new(
            "INVALID_SERVER_URL",
            "服务地址不能包含账号、查询参数或锚点",
        ));
    }
    let localhost = matches!(url.host_str(), Some("localhost" | "127.0.0.1" | "::1"));
    if url.scheme() != "https" && !(cfg!(debug_assertions) && localhost && url.scheme() == "http") {
        return Err(DesktopError::new(
            "HTTPS_REQUIRED",
            "正式客户端仅允许连接 HTTPS 服务",
        ));
    }
    Ok(trimmed.to_string())
}

fn endpoint_url(server_url: &str, path: &str) -> Result<Url, DesktopError> {
    if !path.starts_with('/') || path.starts_with("//") {
        return Err(DesktopError::new("INVALID_API_PATH", "API 路径无效"));
    }
    Url::parse(&format!("{server_url}/api{path}"))
        .map_err(|_| DesktopError::new("INVALID_API_PATH", "API 地址无效"))
}

fn map_network_error(error: reqwest::Error) -> DesktopError {
    let detail = error.to_string();
    if error.is_timeout() {
        DesktopError::new("NETWORK_TIMEOUT", "连接服务器超时，请检查网络或稍后重试")
    } else if detail.to_lowercase().contains("dns") {
        DesktopError::new("NETWORK_DNS", "无法解析服务器域名，请检查服务地址和网络")
    } else if detail.to_lowercase().contains("certificate") || detail.to_lowercase().contains("tls")
    {
        DesktopError::new("NETWORK_TLS", "服务器 HTTPS 证书校验失败")
    } else if error.is_connect() {
        DesktopError::new("NETWORK_UNREACHABLE", "无法连接服务器，请确认服务已启动")
    } else {
        DesktopError::new("NETWORK_ERROR", format!("网络请求失败：{detail}"))
    }
}

fn response_headers(headers: &HeaderMap) -> HashMap<String, String> {
    headers
        .iter()
        .filter_map(|(key, value)| {
            value
                .to_str()
                .ok()
                .map(|value| (key.to_string(), value.to_string()))
        })
        .collect()
}

fn csrf_token(cookies: &CookieStoreMutex, url: &Url) -> Option<String> {
    cookies
        .lock()
        .ok()?
        .get_request_values(url)
        .find(|(name, _)| *name == "csrftoken")
        .map(|(_, value)| value.to_string())
}

#[tauri::command]
async fn get_desktop_config(
    state: State<'_, DesktopState>,
) -> Result<DesktopConfigResponse, DesktopError> {
    let inner = state.inner.lock().await;
    let download_dir = inner
        .config
        .download_dir
        .clone()
        .unwrap_or_else(|| default_download_dir().to_string_lossy().into_owned());
    Ok(DesktopConfigResponse {
        configured: inner.config.server_url.is_some(),
        server_url: inner.config.server_url.clone(),
        download_dir,
        remember_session: inner.config.remember_session,
        version: env!("CARGO_PKG_VERSION").to_string(),
    })
}

#[tauri::command]
async fn configure_server(
    server_url: String,
    state: State<'_, DesktopState>,
) -> Result<DesktopConfigResponse, DesktopError> {
    let validated = validate_server_url(&server_url)?;
    let health_url = Url::parse(&format!("{validated}/health/ready"))
        .map_err(|_| DesktopError::new("INVALID_SERVER_URL", "服务地址无效"))?;
    let response = Client::builder()
        .connect_timeout(Duration::from_secs(8))
        .timeout(Duration::from_secs(12))
        .build()
        .map_err(|error| DesktopError::new("HTTP_CLIENT_FAILED", error.to_string()))?
        .get(health_url)
        .send()
        .await
        .map_err(map_network_error)?;
    if !response.status().is_success() {
        return Err(DesktopError::status(
            "SERVER_NOT_READY",
            format!(
                "服务器健康检查未通过（HTTP {}）",
                response.status().as_u16()
            ),
            response.status().as_u16(),
        ));
    }

    // Verify the response is a real EduAgentX health check, not an SPA fallback
    let content_type = response
        .headers()
        .get("content-type")
        .and_then(|v| v.to_str().ok())
        .unwrap_or("")
        .to_string();
    if !content_type.contains("application/json") {
        return Err(DesktopError::new(
            "SERVER_INVALID_RESPONSE",
            "服务器返回了非 JSON 响应，请确认服务地址指向 EduAgentX 后端",
        ));
    }
    let body: Value = response
        .json()
        .await
        .map_err(|_| DesktopError::new("SERVER_INVALID_RESPONSE", "无法解析服务器健康检查响应"))?;
    if body.get("status").and_then(Value::as_str) != Some("ready") {
        return Err(DesktopError::new(
            "SERVER_NOT_READY",
            format!("服务器尚未就绪: {}", body),
        ));
    }

    // Verify this is an EduAgentX server (version handshake)
    let service = body.get("service").and_then(Value::as_str).unwrap_or("");
    let api_version = body.get("api_version").and_then(Value::as_str).unwrap_or("");
    if !service.contains("eduagentx") || !api_version.starts_with("4.") {
        return Err(DesktopError::new(
            "SERVER_INCOMPATIBLE",
            "服务器健康检查响应不包含 EduAgentX 标识或 API 版本不兼容，请确认地址指向 EduAgentX 后端",
        ));
    }

    let mut inner = state.inner.lock().await;
    if inner.config.server_url.as_deref() != Some(validated.as_str()) {
        delete_persisted_cookies();
        inner.cookies = Arc::new(CookieStoreMutex::new(CookieStore::default()));
        inner.client = build_client(Arc::clone(&inner.cookies))?;
        inner.config.remember_session = false;
    }
    inner.config.server_url = Some(validated);
    write_config(&state.config_path, &inner.config)?;
    let download_dir = inner
        .config
        .download_dir
        .clone()
        .unwrap_or_else(|| default_download_dir().to_string_lossy().into_owned());
    Ok(DesktopConfigResponse {
        configured: true,
        server_url: inner.config.server_url.clone(),
        download_dir,
        remember_session: inner.config.remember_session,
        version: env!("CARGO_PKG_VERSION").to_string(),
    })
}

#[tauri::command]
async fn choose_download_directory(
    state: State<'_, DesktopState>,
) -> Result<Option<String>, DesktopError> {
    let selected = tokio::task::spawn_blocking(|| rfd::FileDialog::new().pick_folder())
        .await
        .map_err(|error| DesktopError::new("DIALOG_FAILED", error.to_string()))?;
    let Some(path) = selected else {
        return Ok(None);
    };
    let mut inner = state.inner.lock().await;
    inner.config.download_dir = Some(path.to_string_lossy().into_owned());
    write_config(&state.config_path, &inner.config)?;
    Ok(inner.config.download_dir.clone())
}

#[tauri::command]
async fn reset_download_directory(state: State<'_, DesktopState>) -> Result<String, DesktopError> {
    let mut inner = state.inner.lock().await;
    inner.config.download_dir = None;
    write_config(&state.config_path, &inner.config)?;
    Ok(default_download_dir().to_string_lossy().into_owned())
}

#[tauri::command]
async fn clear_desktop_session(state: State<'_, DesktopState>) -> Result<(), DesktopError> {
    let mut inner = state.inner.lock().await;
    delete_persisted_cookies();
    inner.cookies = Arc::new(CookieStoreMutex::new(CookieStore::default()));
    inner.client = build_client(Arc::clone(&inner.cookies))?;
    inner.config.remember_session = false;
    write_config(&state.config_path, &inner.config)
}

#[tauri::command]
async fn native_api_request(
    request: NativeApiRequest,
    state: State<'_, DesktopState>,
) -> Result<NativeApiResponse, DesktopError> {
    let (server_url, client, cookies) =
        {
            let inner = state.inner.lock().await;
            (
                inner.config.server_url.clone().ok_or_else(|| {
                    DesktopError::new("SERVER_NOT_CONFIGURED", "请先配置服务器地址")
                })?,
                inner.client.clone(),
                Arc::clone(&inner.cookies),
            )
        };
    let url = endpoint_url(&server_url, &request.path)?;
    let method = Method::from_bytes(request.method.as_bytes())
        .map_err(|_| DesktopError::new("INVALID_HTTP_METHOD", "请求方法无效"))?;
    let mut builder = client
        .request(method.clone(), url.clone())
        .timeout(Duration::from_millis(
            request.timeout_ms.unwrap_or(DEFAULT_TIMEOUT_SECONDS * 1000),
        ));
    for (name, value) in request.headers {
        builder = builder.header(name, value);
    }
    if !matches!(method, Method::GET | Method::HEAD | Method::OPTIONS) {
        if let Some(token) = csrf_token(&cookies, &url) {
            builder = builder.header("X-CSRF-Token", token);
        }
    }
if let Some(parts) = request.multipart {
    let mut form = reqwest::multipart::Form::new();
    for part in parts {
        if let Some(path) = part.file_path {
            // Read file directly from disk to avoid Base64 encoding overhead.
            // This is more efficient for large files (PDF, video, datasets).
            let bytes = fs::read(&path)
                .await
                .map_err(|error| DesktopError::new("FILE_READ_FAILED", error.to_string()))?;
            let mut file = reqwest::multipart::Part::bytes(bytes);
            if let Some(filename) = part.filename {
                file = file.file_name(filename);
            }
            if let Some(content_type) = part.content_type {
                file = file
                    .mime_str(&content_type)
                    .map_err(|_| DesktopError::new("INVALID_UPLOAD", "上传文件类型无效"))?;
            }
            form = form.part(part.name, file);
        } else if let Some(encoded) = part.bytes_base64 {
            let bytes = BASE64
                .decode(encoded)
                .map_err(|_| DesktopError::new("INVALID_UPLOAD", "上传文件编码无效"))?;
            let mut file = reqwest::multipart::Part::bytes(bytes);
            if let Some(filename) = part.filename {
                file = file.file_name(filename);
            }
            if let Some(content_type) = part.content_type {
                file = file
                    .mime_str(&content_type)
                    .map_err(|_| DesktopError::new("INVALID_UPLOAD", "上传文件类型无效"))?;
            }
            form = form.part(part.name, file);
        } else {
            form = form.text(part.name, part.value.unwrap_or_default());
        }
    }
    builder = builder.multipart(form);
    } else if let Some(body) = request.body.as_ref() {
        builder = builder.body(body.clone());
    }

    let remember_requested = request.path == "/auth/login"
        && request
            .body
            .as_ref()
            .and_then(|body| serde_json::from_str::<Value>(body).ok())
            .and_then(|value| value.get("remember_me").and_then(Value::as_bool))
            .unwrap_or(false);
    let is_logout = request.path == "/auth/logout";
    let response = builder.send().await.map_err(map_network_error)?;
    let status = response.status().as_u16();
    let headers = response_headers(response.headers());
    let body = response.text().await.map_err(map_network_error)?;

    if request.path == "/auth/login" && (200..300).contains(&status) {
        let mut inner = state.inner.lock().await;
        inner.config.remember_session = remember_requested;
        if remember_requested {
            save_persisted_cookies(&cookies)?;
        } else {
            delete_persisted_cookies();
        }
        write_config(&state.config_path, &inner.config)?;
    } else if request.path == "/auth/refresh" && (200..300).contains(&status) {
        let inner = state.inner.lock().await;
        if inner.config.remember_session {
            save_persisted_cookies(&cookies)?;
        }
    } else if is_logout && (200..300).contains(&status) {
        let mut inner = state.inner.lock().await;
        delete_persisted_cookies();
        inner.cookies = Arc::new(CookieStoreMutex::new(CookieStore::default()));
        inner.client = build_client(Arc::clone(&inner.cookies))?;
        inner.config.remember_session = false;
        write_config(&state.config_path, &inner.config)?;
    }

    Ok(NativeApiResponse {
        status,
        headers,
        body,
    })
}

fn safe_filename(value: &str) -> String {
    let invalid = Regex::new(r#"[<>:\"/|?*\x00-\x1f]"#).expect("valid filename regex");
    let sanitized = invalid
        .replace_all(value, "_")
        .trim()
        .trim_matches('.')
        .to_string();
    if sanitized.is_empty() {
        "EduAgentX-resource".to_string()
    } else {
        sanitized
    }
}

async fn download_to_path(
    client: &Client,
    cookies: &CookieStoreMutex,
    url: Url,
    destination: &Path,
) -> Result<(), DesktopError> {
    let mut request = client.get(url.clone());
    if let Some(token) = csrf_token(cookies, &url) {
        request = request.header("X-CSRF-Token", token);
    }
    let response = request.send().await.map_err(map_network_error)?;
    if !response.status().is_success() {
        return Err(DesktopError::status(
            "DOWNLOAD_FAILED",
            format!("文件下载失败（HTTP {}）", response.status().as_u16()),
            response.status().as_u16(),
        ));
    }
    // Capture expected content length for validation
    let expected_length = response
        .headers()
        .get("content-length")
        .and_then(|v| v.to_str().ok())
        .and_then(|s| s.parse::<u64>().ok());
    if let Some(parent) = destination.parent() {
        fs::create_dir_all(parent)
            .await
            .map_err(|error| DesktopError::new("DOWNLOAD_DIR_FAILED", error.to_string()))?;
    }
    let partial = destination.with_extension(format!(
        "{}.part",
        destination
            .extension()
            .and_then(|value| value.to_str())
            .unwrap_or("download")
    ));

    // Use a guard to ensure cleanup on error
    let result = download_inner(response, &partial, expected_length).await;
    if result.is_err() {
        // Immediately clean up the .part file on failure
        let _ = fs::remove_file(&partial).await;
        return result;
    }

    // Atomically rename .part to final destination
    if fs::try_exists(destination).await.unwrap_or(false) {
        fs::remove_file(destination)
            .await
            .map_err(|error| DesktopError::new("FILE_REPLACE_FAILED", error.to_string()))?;
    }
    fs::rename(&partial, destination)
        .await
        .map_err(|error| DesktopError::new("FILE_SAVE_FAILED", error.to_string()))
}

async fn download_inner(
    response: reqwest::Response,
    partial: &Path,
    expected_length: Option<u64>,
) -> Result<(), DesktopError> {
    let mut file = fs::File::create(partial)
        .await
        .map_err(|error| DesktopError::new("FILE_SAVE_FAILED", error.to_string()))?;
    let mut stream = response.bytes_stream();
    let mut total_written: u64 = 0;
    while let Some(chunk) = stream.next().await {
        let chunk = chunk.map_err(map_network_error)?;
        file.write_all(&chunk)
            .await
            .map_err(|error| DesktopError::new("FILE_SAVE_FAILED", error.to_string()))?;
        total_written += chunk.len() as u64;
    }
    file.flush()
        .await
        .map_err(|error| DesktopError::new("FILE_SAVE_FAILED", error.to_string()))?;
    drop(file);

    // Validate content length if provided by the server
    if let Some(expected) = expected_length {
        if total_written != expected {
            return Err(DesktopError::new(
                "DOWNLOAD_SIZE_MISMATCH",
                format!(
                    "下载文件大小不匹配：期望 {} 字节，实际 {} 字节",
                    expected, total_written
                ),
            ));
        }
    }

    Ok(())
}

#[tauri::command]
async fn native_download_resource(
    app: AppHandle,
    path: String,
    suggested_filename: String,
    save_as: bool,
    state: State<'_, DesktopState>,
) -> Result<Option<DownloadResult>, DesktopError> {
    let (server_url, default_dir, client, cookies) =
        {
            let inner = state.inner.lock().await;
            (
                inner.config.server_url.clone().ok_or_else(|| {
                    DesktopError::new("SERVER_NOT_CONFIGURED", "请先配置服务器地址")
                })?,
                inner
                    .config
                    .download_dir
                    .as_ref()
                    .map(PathBuf::from)
                    .unwrap_or_else(default_download_dir),
                inner.client.clone(),
                Arc::clone(&inner.cookies),
            )
        };
    let url = endpoint_url(&server_url, &path)?;
    let filename = safe_filename(&suggested_filename);
    // Always download into an app-specific subdirectory so that open_file's
    // directory whitelist (Downloads/EduAgentX/) matches the actual save path.
    let app_download_dir = default_dir.join("EduAgentX");
    fs::create_dir_all(&app_download_dir)
        .await
        .map_err(|error| DesktopError::new("DOWNLOAD_DIR_FAILED", error.to_string()))?;
    let destination = if save_as {
        let initial = app_download_dir.join(&filename);
        tokio::task::spawn_blocking(move || {
            rfd::FileDialog::new()
                .set_file_name(
                    initial
                        .file_name()
                        .and_then(|value| value.to_str())
                        .unwrap_or("resource"),
                )
                .set_directory(initial.parent().unwrap_or(Path::new(".")))
                .save_file()
        })
        .await
        .map_err(|error| DesktopError::new("DIALOG_FAILED", error.to_string()))?
    } else {
        Some(app_download_dir.join(&filename))
    };
    let Some(destination) = destination else {
        return Ok(None);
    };
    download_to_path(&client, &cookies, url, &destination).await?;
    let _ = app
        .notification()
        .builder()
        .title("EduAgentX")
        .body(format!(
            "文件已保存：{}",
            destination
                .file_name()
                .and_then(|value| value.to_str())
                .unwrap_or(&filename)
        ))
        .show();
    Ok(Some(DownloadResult {
        path: destination.to_string_lossy().into_owned(),
        filename,
    }))
}

#[tauri::command]
async fn cache_resource(
    path: String,
    cache_key: String,
    extension: String,
    content_hash: Option<String>,
    state: State<'_, DesktopState>,
) -> Result<String, DesktopError> {
    let (server_url, client, cookies) =
        {
            let inner = state.inner.lock().await;
            (
                inner.config.server_url.clone().ok_or_else(|| {
                    DesktopError::new("SERVER_NOT_CONFIGURED", "请先配置服务器地址")
                })?,
                inner.client.clone(),
                Arc::clone(&inner.cookies),
            )
        };
    let url = endpoint_url(&server_url, &path)?;
    let cache_name = if let Some(hash) = content_hash {
        // Include content hash in cache filename so that regenerated resources
        // with the same key but different content get a new cache entry.
        format!(
            "{}_{}.{}",
            safe_filename(&cache_key),
            safe_filename(&hash),
            safe_filename(&extension)
        )
    } else {
        format!(
            "{}.{}",
            safe_filename(&cache_key),
            safe_filename(&extension)
        )
    };
    let destination = state.cache_dir.join("media").join(cache_name);
    if !fs::try_exists(&destination).await.unwrap_or(false) {
        download_to_path(&client, &cookies, url, &destination).await?;
        // Enforce cache limit after each download
        enforce_cache_limit(&state.cache_dir).await;
    }
    Ok(destination.to_string_lossy().into_owned())
}

#[tauri::command]
fn open_file(path: String, state: State<'_, DesktopState>) -> Result<(), DesktopError> {
    let canonical = PathBuf::from(path)
        .canonicalize()
        .map_err(|_| DesktopError::new("FILE_NOT_FOUND", "文件不存在或已被移动"))?;
    if !canonical.is_file() {
        return Err(DesktopError::new("FILE_NOT_FOUND", "目标不是可打开的文件"));
    }

    // --- Security: File extension whitelist ---
    let extension = canonical
        .extension()
        .and_then(|ext| ext.to_str())
        .map(|ext| format!(".{}", ext.to_lowercase()))
        .unwrap_or_default();

    if BLOCKED_FILE_EXTENSIONS.contains(&extension.as_str()) {
        return Err(DesktopError::new(
            "FILE_TYPE_BLOCKED",
            format!("出于安全考虑，不允许打开此类型文件: {}", extension),
        ));
    }

    if !ALLOWED_FILE_EXTENSIONS.contains(&extension.as_str()) {
        return Err(DesktopError::new(
            "FILE_TYPE_NOT_ALLOWED",
            format!("不支持打开此类型文件: {}。允许的类型: PDF, PPTX, DOCX, ZIP, MP4, PNG, JPG, TXT 等", extension),
        ));
    }

    // --- Security: Directory whitelist ---
    // Only allow opening files from the app's cache directory or a dedicated
    // EduAgentX subdirectory within the user's download directory.
    // All whitelist roots are canonicalized to avoid mismatches on Windows
    // (e.g. \\?\ prefixes, drive letter case, symlinks).
    let cache_dir = state.cache_dir.clone();
    let media_cache = cache_dir.join("media");
    let download_dir = state
        .inner
        .try_lock()
        .ok()
        .and_then(|inner| inner.config.download_dir.clone().map(PathBuf::from))
        .unwrap_or_else(default_download_dir);
    // Restrict to an app-specific subdirectory under downloads, not the entire downloads folder
    let app_download_dir = download_dir.join("EduAgentX");

    // Canonicalize all allowed roots — fall back to the non-canonical path
    // if the directory doesn't exist yet (e.g. no downloads yet).
    let canonical_media = media_cache.canonicalize().unwrap_or(media_cache);
    let canonical_app_dl = app_download_dir.canonicalize().unwrap_or(app_download_dir);
    let canonical_cache = cache_dir.canonicalize().unwrap_or(cache_dir);

    let is_in_allowed_dir = canonical.starts_with(&canonical_media)
        || canonical.starts_with(&canonical_app_dl)
        || canonical.starts_with(&canonical_cache);

    if !is_in_allowed_dir {
        // For files outside the whitelist (e.g. "Save As" to a custom directory),
        // offer to reveal the file in the system file manager instead of opening directly.
        if let Some(parent) = canonical.parent() {
            open::that(parent)
                .map_err(|error| DesktopError::new("FILE_OPEN_FAILED", error.to_string()))?;
            return Err(DesktopError::new(
                "FILE_PATH_NOT_ALLOWED",
                "文件不在 EduAgentX 管理目录中，已在资源管理器中显示其所在文件夹。请手动打开该文件。",
            ));
        }
        return Err(DesktopError::new(
            "FILE_PATH_NOT_ALLOWED",
            "只能打开 EduAgentX 下载或缓存目录中的文件。",
        ));
    }

    open::that(canonical).map_err(|error| DesktopError::new("FILE_OPEN_FAILED", error.to_string()))
}

/// Clean up stale .part files in the cache directory on startup
async fn cleanup_stale_part_files(cache_dir: &Path) {
    let media_dir = cache_dir.join("media");
    if !fs::try_exists(&media_dir).await.unwrap_or(false) {
        return;
    }
    let mut entries = match fs::read_dir(&media_dir).await {
        Ok(entries) => entries,
        Err(_) => return,
    };
    while let Ok(Some(entry)) = entries.next_entry().await {
        let path = entry.path();
        if let Some(name) = path.file_name().and_then(|n| n.to_str()) {
            if name.ends_with(".part") {
                if let Ok(metadata) = entry.metadata().await {
                    if let Ok(modified) = metadata.modified() {
                        if modified.elapsed().unwrap_or_default().as_secs()
                            > PART_FILE_MAX_AGE_SECONDS
                        {
                            let _ = fs::remove_file(&path).await;
                        }
                    }
                }
            }
        }
    }
}

/// Enforce cache size limit by removing oldest files (LRU)
async fn enforce_cache_limit(cache_dir: &Path) {
    let media_dir = cache_dir.join("media");
    if !fs::try_exists(&media_dir).await.unwrap_or(false) {
        return;
    }
    let mut files: Vec<(PathBuf, u64, std::time::SystemTime)> = Vec::new();
    let mut total_size: u64 = 0;
    let mut entries = match fs::read_dir(&media_dir).await {
        Ok(entries) => entries,
        Err(_) => return,
    };
    while let Ok(Some(entry)) = entries.next_entry().await {
        let path = entry.path();
        if path.is_file() {
            if let Ok(metadata) = entry.metadata().await {
                let size = metadata.len();
                let modified = metadata.modified().unwrap_or(std::time::SystemTime::UNIX_EPOCH);
                total_size += size;
                files.push((path, size, modified));
            }
        }
    }
    if total_size <= MAX_CACHE_SIZE_BYTES {
        return;
    }
    // Sort by modified time (oldest first)
    files.sort_by_key(|(_, _, modified)| *modified);
    for (path, size, _) in &files {
        if total_size <= MAX_CACHE_SIZE_BYTES {
            break;
        }
        let _ = fs::remove_file(path).await;
        total_size -= *size;
    }
}

#[tauri::command]
async fn clear_cache(state: State<'_, DesktopState>) -> Result<u64, DesktopError> {
    let media_dir = state.cache_dir.join("media");
    let mut freed: u64 = 0;
    if !fs::try_exists(&media_dir).await.unwrap_or(false) {
        return Ok(0);
    }
    let mut entries = fs::read_dir(&media_dir)
        .await
        .map_err(|e| DesktopError::new("CACHE_CLEAR_FAILED", e.to_string()))?;
    while let Ok(Some(entry)) = entries.next_entry().await {
        let path = entry.path();
        if let Ok(metadata) = entry.metadata().await {
            freed += metadata.len();
        }
        let _ = fs::remove_file(&path).await;
    }
    Ok(freed)
}

#[tauri::command]
async fn get_cache_size(state: State<'_, DesktopState>) -> Result<u64, DesktopError> {
    let media_dir = state.cache_dir.join("media");
    if !fs::try_exists(&media_dir).await.unwrap_or(false) {
        return Ok(0);
    }
    let mut total: u64 = 0;
    let mut entries = fs::read_dir(&media_dir)
        .await
        .map_err(|e| DesktopError::new("CACHE_READ_FAILED", e.to_string()))?;
    while let Ok(Some(entry)) = entries.next_entry().await {
        if let Ok(metadata) = entry.metadata().await {
            total += metadata.len();
        }
    }
    Ok(total)
}

#[tauri::command]
fn show_system_notification(
    app: AppHandle,
    title: String,
    body: String,
) -> Result<(), DesktopError> {
    app.notification()
        .builder()
        .title(title)
        .body(body)
        .show()
        .map_err(|error| DesktopError::new("NOTIFICATION_FAILED", error.to_string()))
}

#[tauri::command]
fn complete_desktop_bootstrap(app: AppHandle) -> Result<(), DesktopError> {
    if let Some(main) = app.get_webview_window("main") {
        main.show()
            .map_err(|error| DesktopError::new("WINDOW_SHOW_FAILED", error.to_string()))?;
        main.set_focus().ok();
    }
    if let Some(splash) = app.get_webview_window("splashscreen") {
        splash
            .close()
            .map_err(|error| DesktopError::new("SPLASH_CLOSE_FAILED", error.to_string()))?;
    }
    Ok(())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let state = DesktopState::load().expect("failed to initialize EduAgentX desktop state");
    // Clean up stale .part files and enforce cache limit on startup
    let cache_dir = state.cache_dir.clone();
    tauri::async_runtime::block_on(async {
        cleanup_stale_part_files(&cache_dir).await;
        enforce_cache_limit(&cache_dir).await;
    });
    tauri::Builder::default()
        .plugin(tauri_plugin_notification::init())
        .manage(state)
        .invoke_handler(tauri::generate_handler![
            get_desktop_config,
            configure_server,
            choose_download_directory,
            reset_download_directory,
            clear_desktop_session,
            native_api_request,
            native_download_resource,
            cache_resource,
            open_file,
            clear_cache,
            get_cache_size,
            show_system_notification,
            complete_desktop_bootstrap,
        ])
        .run(tauri::generate_context!())
        .expect("error while running EduAgentX desktop client");
}
