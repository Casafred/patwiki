// PatWiki Tauri 主程序
// 职责：
// 1. 启动时拉起后端 (patwiki-backend.exe，由 PyInstaller 打包)
// 2. 健康检查后端就绪后加载前端
// 3. 应用退出时优雅终止后端进程

use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::time::{Duration, Instant};
use sysinfo::{ProcessesToUpdate, System};
use tauri::Manager;

const BACKEND_PORT: u16 = 8765;
const HEALTH_CHECK_TIMEOUT_SECS: u64 = 60;

/// 找到后端可执行文件路径
/// - 开发模式：../backend/dist/patwiki-backend/patwiki-backend.exe
/// - 打包后：应用资源目录 / patwiki-backend/patwiki-backend.exe
fn resolve_backend_path(app: &tauri::App) -> Option<PathBuf> {
    let exe_name = if cfg!(windows) {
        "patwiki-backend.exe"
    } else {
        "patwiki-backend"
    };

    // 1. 打包后：resource_dir/patwiki-backend/patwiki-backend.exe
    if let Ok(resource_dir) = app.path().resource_dir() {
        let p = resource_dir.join("patwiki-backend").join(exe_name);
        if p.exists() {
            return Some(p);
        }
    }

    // 2. 开发模式：项目根/backend/dist/patwiki-backend/patwiki-backend.exe
    let dev_path = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .parent()? // 去掉 src-tauri
        .join("backend")
        .join("dist")
        .join("patwiki-backend")
        .join(exe_name);
    if dev_path.exists() {
        return Some(dev_path);
    }

    None
}

/// 启动后端
fn spawn_backend(app: &tauri::App) -> std::io::Result<Child> {
    let backend_path = resolve_backend_path(app).ok_or_else(|| {
        std::io::Error::new(
            std::io::ErrorKind::NotFound,
            "未找到后端可执行文件 patwiki-backend，请先打包 backend",
        )
    })?;

    println!("[PatWiki] 后端路径: {:?}", backend_path);

    Command::new(backend_path)
        .env("PATWIKI_PORT", BACKEND_PORT.to_string())
        .stdout(Stdio::inherit())
        .stderr(Stdio::inherit())
        .spawn()
}

/// 轮询后端健康检查接口，直到就绪或超时
fn wait_for_backend_ready() -> bool {
    let url = format!("http://127.0.0.1:{}/health", BACKEND_PORT);
    let start = Instant::now();
    let timeout = Duration::from_secs(HEALTH_CHECK_TIMEOUT_SECS);

    let client = reqwest::blocking::Client::builder()
        .timeout(Duration::from_secs(2))
        .build()
        .unwrap();

    while start.elapsed() < timeout {
        if let Ok(resp) = client.get(&url).send() {
            if resp.status().is_success() {
                println!("[PatWiki] 后端就绪");
                return true;
            }
        }
        std::thread::sleep(Duration::from_millis(500));
    }
    false
}

/// 终止后端进程树
fn kill_backend(child: &mut Child) {
    let pid = child.id();
    let _ = child.kill();
    let _ = child.wait();

    // Windows 下用 taskkill 强制终止子进程树
    #[cfg(target_os = "windows")]
    {
        let _ = Command::new("taskkill")
            .args(["/PID", &pid.to_string(), "/T", "/F"])
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status();
    }
}

/// 扫描并杀掉遗留的 patwiki-backend 进程
fn kill_orphaned_backend() {
    let mut sys = System::new_all();
    sys.refresh_processes(ProcessesToUpdate::All, true);

    let target_name = if cfg!(windows) {
        "patwiki-backend.exe"
    } else {
        "patwiki-backend"
    };

    for (_, process) in sys.processes() {
        if process.name().to_string_lossy() == target_name {
            if process.kill() {
                println!("[PatWiki] 清理遗留后端进程");
            }
        }
    }
}

#[tauri::command]
fn get_backend_port() -> u16 {
    BACKEND_PORT
}

/// 后端子进程状态
struct BackendState(Mutex<Option<Child>>);

pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_fs::init())
        .invoke_handler(tauri::generate_handler![get_backend_port])
        .setup(|app| {
            // 启动前先清理可能的遗留进程
            kill_orphaned_backend();

            println!("[PatWiki] 启动后端...");
            let child = spawn_backend(app).map_err(|e| {
                eprintln!("[PatWiki] 启动后端失败: {}", e);
                e
            })?;

            if !wait_for_backend_ready() {
                eprintln!("[PatWiki] 后端启动超时");
                let mut child = child;
                kill_backend(&mut child);
                return Err("后端启动超时".into());
            }

            app.manage(BackendState(Mutex::new(Some(child))));
            Ok(())
        })
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::CloseRequested { .. } = event {
                if let Some(state) = window.app_handle().try_state::<BackendState>() {
                    println!("[PatWiki] 窗口关闭，清理后端进程");
                    if let Ok(mut guard) = state.0.lock() {
                        if let Some(child) = guard.as_mut() {
                            kill_backend(child);
                        }
                        *guard = None;
                    }
                }
            }
        })
        .run(tauri::generate_context!())
        .expect("运行 Tauri 应用时出错");
}

fn main() {
    run();
}
