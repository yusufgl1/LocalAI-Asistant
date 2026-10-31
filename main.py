import os
import sys
import re
import time
import threading
import pyodbc
from typing import List, Dict, Generator, Tuple
import ollama
from fastapi import FastAPI
from fastapi.responses import StreamingResponse, HTMLResponse, JSONResponse
from pydantic import BaseModel
import uvicorn


app = FastAPI(title="LOCAL AI - Hibrit Yazılım Denetim Stüdyosu")

HTTP_P = "http" + "://"
HTTPS_P = "https" + "://"
PORT = 8080
LOCAL_URL = f"{HTTP_P}127.0.0.1:{PORT}"


LOCAL_MODEL = "gemma2:9b"
PROJECT_ROOT = r"C:\LocalAI\Projects"

SQL_CONN_STR = (
    "DRIVER={ODBC Driver 17 for SQL Server};"
    "SERVER=DESKTOP-MB05P67;"
    "DATABASE=LocalAI;"
    "Trusted_Connection=yes;"
    "TrustServerCertificate=yes;"
)

MAX_FILE_CHARS = 25000
MAX_SEARCH_RESULTS = 40
MAX_FILE_BYTES_FOR_SEARCH = 2_000_000

IGNORED_DIRS = {
    ".git", ".vs", ".idea", "__pycache__", "node_modules",
    "bin", "obj", "venv", ".venv", "env", ".env", "dist", "build"
}

SEARCHABLE_EXTENSIONS = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".cs", ".cpp", ".c",
    ".h", ".hpp", ".java", ".sql", ".json", ".xml", ".yaml",
    ".yml", ".ini", ".cfg", ".txt", ".md", ".html", ".css"
}

def save_exchange(user_msg: str, assistant_msg: str) -> str:
    if not user_msg.strip() or not assistant_msg.strip():
        return "Boş mesaj kaydedilmedi."
    conn = None
    try:
        conn = pyodbc.connect(SQL_CONN_STR, timeout=3)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO dbo.Cons (Role, MessagesSent, Tarih) VALUES (?, ?, GETDATE())",
            ("user", user_msg.strip())
        )
        cursor.execute(
            "INSERT INTO dbo.Cons (Role, MessagesSent, Tarih) VALUES (?, ?, GETDATE())",
            ("assistant", assistant_msg.strip())
        )
        conn.commit()
        return ""
    except Exception as e:
        return f"[SQL KAYIT HATASI]: {e}"
    finally:
        if conn:
            conn.close()

def load_messages(limit: int = 4) -> List[Dict[str, str]]:
    conn = None
    try:
        conn = pyodbc.connect(SQL_CONN_STR, timeout=3)
        cursor = conn.cursor()
        cursor.execute(f"""
            SELECT TOP ({int(limit)}) Role, MessagesSent 
            FROM dbo.Cons WITH (NOLOCK) 
            ORDER BY Id DESC
        """)
        rows = cursor.fetchall()
        rows.reverse()
        return [{"role": r[0], "content": r[1]} for r in rows if r[1]]
    except Exception:
        return []
    finally:
        if conn:
            conn.close()

def clear_memory() -> str:
    conn = None
    try:
        conn = pyodbc.connect(SQL_CONN_STR, timeout=3)
        cursor = conn.cursor()
        cursor.execute("TRUNCATE TABLE dbo.Cons")
        conn.commit()
        return "Hafıza sıfırlandı evlat, tabloları tertemiz yaptım. ⬛"
    except Exception as e:
        return f"[SQL TEMİZLEME HATASI]: {e}"
    finally:
        if conn:
            conn.close()

def inspect_sql_schema() -> str:
    conn = None
    try:
        conn = pyodbc.connect(SQL_CONN_STR, timeout=3)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                t.name AS TableName,
                c.name AS ColumnName,
                ty.name AS DataType,
                c.max_length AS MaxLen,
                c.is_identity AS IsIdentity,
                CASE WHEN EXISTS (
                    SELECT 1 FROM sys.indexes i 
                    WHERE i.object_id = t.object_id AND i.is_primary_key = 1
                ) THEN 'Tanımlı' ELSE 'YOK (Heap Tablo - PK Eksik!)' END AS PKStatus,
                (SELECT COUNT(*) FROM sys.indexes i WHERE i.object_id = t.object_id AND i.type > 0) AS IndexCount
            FROM sys.tables t WITH (NOLOCK)
            INNER JOIN sys.columns c WITH (NOLOCK) ON t.object_id = c.object_id
            INNER JOIN sys.types ty WITH (NOLOCK) ON c.user_type_id = ty.user_type_id
            WHERE t.is_ms_shipped = 0
            ORDER BY t.name, c.column_id
        """)
        rows = cursor.fetchall()
        if not rows:
            return "Veritabanında kullanıcı tablosu bulunamadı."

        tables = {}
        for r in rows:
            t_name, c_name, d_type, max_len, is_id, pk_stat, idx_cnt = r
            if t_name not in tables:
                tables[t_name] = {"pk": pk_stat, "idx_count": idx_cnt, "cols": []}
            id_str = " [IDENTITY]" if is_id else ""
            if max_len == -1:
                len_str = "(MAX)"
            elif d_type in ("nvarchar", "nchar"):
                len_str = f"({max_len // 2})"
            elif d_type in ("varchar", "char"):
                len_str = f"({max_len})"
            else:
                len_str = ""
            tables[t_name]["cols"].append(f"{c_name} ({d_type}{len_str}{id_str})")

        report_lines = []
        for t_name, info in tables.items():
            cols_joined = ", ".join(info["cols"])
            report_lines.append(
                f"- TABLO: dbo.{t_name} | Primary Key Durumu: {info['pk']} | Aktif İndeks Sayısı: {info['idx_count']}\n"
                f"  Kolonlar: {cols_joined}"
            )
        return "\n".join(report_lines)
    except Exception as e:
        return f"Şema okunurken hata oluştu: {e}"
    finally:
        if conn:
            conn.close()


def list_projects() -> List[str]:
    if not os.path.exists(PROJECT_ROOT):
        return []
    try:
        return sorted([
            item for item in os.listdir(PROJECT_ROOT)
            if os.path.isdir(os.path.join(PROJECT_ROOT, item)) and item not in IGNORED_DIRS
        ], key=str.lower)
    except Exception:
        return []

def iter_project_files(project_path: str) -> Generator[str, None, None]:
    for root, dirs, files in os.walk(project_path):
        dirs[:] = [d for d in dirs if d not in IGNORED_DIRS]
        for filename in files:
            if filename.lower().endswith((".designer.cs", ".g.cs", ".g.i.cs", "assemblyinfo.cs")):
                continue
            full_path = os.path.join(root, filename)
            ext = os.path.splitext(filename)[1].lower()
            if ext in SEARCHABLE_EXTENSIONS:
                try:
                    if os.path.getsize(full_path) <= MAX_FILE_BYTES_FOR_SEARCH:
                        yield full_path
                except OSError:
                    continue

def read_file_safe(path: str, max_chars: int = MAX_FILE_CHARS) -> str:
    for enc in ("utf-8-sig", "utf-8", "cp1254", "latin-1"):
        try:
            with open(path, "r", encoding=enc) as f:
                return f.read(max_chars)
        except Exception:
            continue
    return ""

def run_static_pre_analysis(rel_path: str, content: str) -> List[str]:
    """
    TÜBİTAK Katmanı: LLM'in halüsinasyon görmesini engellemek için 
    kod üzerindeki gerçek riskleri deterministik kurallarla tespit eder.
    """
    findings = []
    if "int.Parse(" in content or "double.Parse(" in content or "Convert.ToInt32(" in content:
        if "TryParse" not in content:
            findings.append(f"[{rel_path}]: Doğrudan Parse kullanımı var; kullanıcı harf veya boş değer girerse FormatException fırlatır ('TryParse' önerilmeli).")
    if "new SqlConnection" in content and "using" not in content and ".Dispose()" not in content:
        findings.append(f"[{rel_path}]: SqlConnection nesnesi 'using' bloğu dışında tanımlanmış; bağlantı havuzu (Connection Pool) sızıntısı riski var.")
    if re.search(r'(SELECT|INSERT|UPDATE|DELETE)\s+.*?\+\s*[a-zA-Z0-9_]+', content, re.IGNORECASE):
        findings.append(f"[{rel_path}]: SQL sorgusu metin birleştirme (+) ile oluşturulmuş; yüksek SQL Injection riski mevcut ('Parameters.AddWithValue' önerilmeli).")
    if re.search(r'catch\s*(\([^)]*\))?\s*\{\s*\}', content):
        findings.append(f"[{rel_path}]: Boş 'catch' bloğu tespit edildi; hatalar yutuluyor.")
    return findings

def review_project_code(project_name: str) -> str:
    proj_dir = os.path.join(PROJECT_ROOT, project_name)
    if not os.path.exists(proj_dir):
        return f"HATA: '{project_name}' dizini bulunamadı."

    file_contents = []
    static_warnings = []
    total_chars = 0
    file_count = 0

    for path in iter_project_files(proj_dir):
        rel_path = os.path.relpath(path, proj_dir)
        content = read_file_safe(path, max_chars=4500)
        if content:
            file_count += 1
            static_warnings.extend(run_static_pre_analysis(rel_path, content))
            file_contents.append(f"--- DOSYA: {rel_path} ---\n{content}\n")
            total_chars += len(content)
            if total_chars > 20000:
                break

    if not file_contents:
        return f"'{project_name}' projesinde incelenebilir kod dosyası bulunamadı."

    static_summary = (
        "DETERMİNİSTİK ÖN ANALİZ BULGULARI (Kesin Doğruluk):\n- " + "\n- ".join(static_warnings)
        if static_warnings
        else "DETERMİNİSTİK ÖN ANALİZ: SQL bağlantısı veya bariz güvenlik açığı tespit edilmedi. Sadece mevcut algoritmayı ve olay (event) metodunu incele."
    )

    return (
        f"PROJE ADI: {project_name} (Taranan Dosya: {file_count})\n"
        f"{static_summary}\n\n" + "\n".join(file_contents)
    )

def search_in_files(search_terms: List[str]) -> Tuple[str, int]:
    projects = list_projects()
    if not projects:
        return f"HATA: '{PROJECT_ROOT}' dizininde proje yok.", 0

    matched_lines = []
    scanned_count = 0

    for project in projects:
        proj_dir = os.path.join(PROJECT_ROOT, project)
        for path in iter_project_files(proj_dir):
            scanned_count += 1
            content = read_file_safe(path)
            if not content:
                continue
            for line_no, line in enumerate(content.splitlines(), start=1):
                line_lower = line.lower()
                if any(t.lower() in line_lower for t in search_terms):
                    rel = os.path.relpath(path, PROJECT_ROOT)
                    matched_lines.append(f"DOSYA: {rel} | SATIR {line_no} -> {line.strip()}")
                    if len(matched_lines) >= MAX_SEARCH_RESULTS:
                        return "\n".join(matched_lines), scanned_count

    if not matched_lines:
        return f"SONUÇ YOK: Aranan terimler ({', '.join(search_terms)}) bulunamadı.", scanned_count

    return "\n".join(matched_lines), scanned_count

def detect_search_intent(question: str) -> Tuple[bool, List[str]]:
    q_lower = question.lower()
    debug_traps = ["nerede hata", "nerede yanlış", "neyi yanlış", "nerede patladık", "neden olur"]
    if any(trap in q_lower for trap in debug_traps):
        return False, []

    has_target = any(k in q_lower for k in ["projemde", "projelerimde", "kodda", "dosyalarda"])
    has_action = any(k in q_lower for k in ["ara", "bul", "geçen yerler", "nerede geçiyor", "nerede tanımlı"])
    quoted = re.findall(r"['\"]([^'\"]+)['\"]", question)

    if (has_target and has_action) or (quoted and (has_target or has_action)):
        if quoted:
            return True, quoted
        terms = [t for t in re.findall(r"[a-zA-Z0-9_çğıöşüÇĞİÖŞÜ.-]+", q_lower) if len(t) >= 2]
        return True, terms

    return False, []


def generate_ai_chunks(question: str) -> Generator[str, None, None]:
    q_lower = question.strip().lower()

    if q_lower in {"/temizle", "temizle", "/reset", "reset"}:
        yield clear_memory()
        return

    is_schema_check = any(k in q_lower for k in ["şema denetimi", "şemasını analiz et", "şema analizi", "/sema"])
    is_code_review = "code review" in q_lower or "incele" in q_lower

    tech_keywords = [
        "sql", "c#", "deadlock", "kilit", "lock", "izolasyon", "isolation",
        "serializable", "rcsi", "transaction", "commit", "tablo", "index", "indeks",
        "query", "veri", "hata", "kod", "proje", "db", "database", "bellek", "sızıntı",
        "memory", "leak", "gc", "garbage", "dispose", "using", "linq", "ef", "api", "şema",
        "textbox", "buton", "button", "form", "güncelle", "ekle", "sil", "update", "insert", "cs0246", "nuget"
    ]
    is_technical = is_schema_check or is_code_review or any(k in q_lower for k in tech_keywords)

    recent_history = []
    dynamic_context = ""

    if is_technical:
        recent_history = load_messages(limit=4)
        if is_schema_check:
            schema_report = inspect_sql_schema()
            dynamic_context = (
                f"CANLI SQL SERVER ŞEMA VE İNDEKS RAPORU (Veritabanı: LocalAI):\n{schema_report}\n\n"
                "Yukarıdaki gerçek tablo ve kolon yapılarını incele. Primary Key (PK) durumu, "
                "veri tipleri ve indeksleme açısından çırağa kısa, maddeli bir teknik değerlendirme sun."
            )
        elif is_code_review:
            projs = list_projects()
            target_proj = None
            for p in projs:
                if p.lower() in q_lower:
                    target_proj = p
                    break
            
            if target_proj:
                review_data = review_project_code(target_proj)
                dynamic_context = (
                    f"OTOMATİK CODE REVIEW VERİSİ:\n{review_data}\n\n"
                    "Yalnızca yukarıdaki dosyalarda gerçekten var olan hataları incele. "
                    "Dosyalarda SQL veya veritabanı kodu yoksa veritabanından bahsetme. "
                    "Sorunları kısa maddeler halinde açıkla ve yalnızca düzeltilmesi gereken metodu ```csharp bloğu içinde göster."
                )
            else:
                dynamic_context = "İncelenecek proje adı bulunamadı."
        elif q_lower in {"projeler", "projelerim", "hangi projeler var"}:
            projs = list_projects()
            dynamic_context = "MEVCUT PROJELER:\n" + ("\n".join(f"- {p}" for p in projs) if projs else "Proje yok.")
        else:
            is_search, search_terms = detect_search_intent(question)
            if is_search:
                report, _ = search_in_files(search_terms)
                dynamic_context = f"KOD ARAMA RAPORU:\n{report}\nBu rapordaki dosya ve satırları çırağa açıkla."

        if any(k in q_lower for k in ["cs0246", "sqlconnection", "sqlclient", "nuget"]):
            dynamic_context += (
                "\nNot: 'SqlConnection türü bulunamadı' (CS0246) hatasında en üste 'using System.Data.SqlClient;' "
                "eklenmesini ve NuGet üzerinden 'Install-Package System.Data.SqlClient' kurulmasını söyle."
            )

        if any(k in q_lower for k in ["deadlock", "kilit", "lock", "izolasyon", "isolation", "serializable", "rcsi", "transaction"]):
            dynamic_context += (
                "\nNot: SQL Server deadlock sorunlarında Serializable izolasyon seviyesinin kilitlenmeleri artıracağını belirt. "
                "Çözüm olarak işlemleri kısa tutmayı, tablo erişim sırasını standartlaştırmayı ve RCSI (Read Committed Snapshot Isolation) kullanmayı öner."
            )

    if is_technical:
        sys_message = (
            "Sen bir yazılım atölyesinin kıdemli başmühendisi ve ustasısın. Karşındaki kişi senin çırağındır.\n"
            "Hitabın daima tekil ve samimidir ('evlat', 'sen').\n"
            "Yanıtını şu akışla oluştur:\n"
            "1. Tespit ettiğin gerçek teknik noktaları kısa maddelerle açıkla.\n"
            "2. Kod örneği gerekiyorsa bütün sınıfı değil, yalnızca ilgili metodu ```csharp bloğu içinde yaz ve bloğu mutlaka kapat.\n"
            "3. Kod bloğunun hemen altına herhangi bir başlık atmadan tek cümlelik bir usta tavsiyesi ekle ve yanıtı bitir."
        )
        if dynamic_context:
            sys_message += f"\n\n---\n{dynamic_context}"
    else:
        sys_message = "Sen kıdemli bir atölye ustasısın. Karşındaki çırağa 'evlat' diye hitap et. Soruya sadece 1-2 cümlelik net ve samimi bir cevap ver."

    messages = [{"role": "system", "content": sys_message}]

    if is_technical and not is_schema_check and not is_code_review:
        messages.extend(recent_history)

    messages.append({"role": "user", "content": question})

    full_response = ""
    try:
        response_stream = ollama.chat(
            model=LOCAL_MODEL,
            messages=messages,
            stream=True,
            keep_alive="15m",  
            options={
                "temperature": 0.1,
                "top_p": 0.80,
                "repeat_penalty": 1.20,
                "repeat_last_n": 64,
                "num_predict": 850,  
                "stop": ["\nSen:", "\nKullanıcı:", "\nÇırak:"]
            }
        )

        for chunk in response_stream:
            token = chunk.get("message", {}).get("content", "")
            full_response += token
            yield token

    except Exception as e:
        yield f"\n[Ollama Hatası]: {e}\n"
    finally:
        if full_response.strip():
            sql_err = save_exchange(question, full_response)
            if sql_err:
                yield f"\n\n{sql_err}"

CDN_MARKED = HTTPS_P + "cdn.jsdelivr.net/npm/marked/marked.min.js"
CDN_HLJS_CSS = HTTPS_P + "cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/github-dark.min.css"
CDN_HLJS_JS = HTTPS_P + "cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/highlight.min.js"

HTML_ARAYUZ = r"""<!DOCTYPE html>
<html lang="tr">
<head>
    <link rel="icon" href="data:,">
    <meta charset="UTF-8">
    <title>LOCAL AI - Hibrit Yazılım Denetim Stüdyosu</title>
    <script src="__CDN_MARKED__"></script>
    <link rel="stylesheet" href="__CDN_HLJS_CSS__">
    <script src="__CDN_HLJS_JS__"></script>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Segoe UI', system-ui, sans-serif; }
        body { background-color: #000000; color: #e5e5e5; display: flex; height: 100vh; overflow: hidden; }
        .sidebar { width: 290px; background-color: #0a0a0a; border-right: 1px solid #222222; display: flex; flex-direction: column; padding: 20px; }
        .logo { font-size: 1.2rem; font-weight: 800; color: #ffffff; display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; letter-spacing: 1px; }
        .logo-badge { font-size: 0.65rem; background: #262626; color: #a3a3a3; padding: 3px 7px; border-radius: 4px; border: 1px solid #404040; }
        .btn-action { background: #171717; color: #f87171; border: 1px solid #262626; padding: 10px 12px; border-radius: 8px; font-weight: 600; cursor: pointer; margin-bottom: 8px; transition: 0.2s; font-size: 0.82rem; text-align: left; }
        .btn-action:hover { background: #262626; color: #ffffff; border-color: #404040; }
        .btn-schema { background: #ffffff; color: #000000; border: 1px solid #ffffff; padding: 10px 12px; border-radius: 8px; font-weight: 700; cursor: pointer; margin-bottom: 16px; transition: 0.2s; font-size: 0.82rem; text-align: left; }
        .btn-schema:hover { background: #d4d4d4; }
        .section-title { font-size: 0.72rem; text-transform: uppercase; color: #737373; font-weight: 700; letter-spacing: 1px; margin-bottom: 8px; margin-top: 8px; }
        .project-list { flex: 1; overflow-y: auto; display: flex; flex-direction: column; gap: 6px; }
        .project-item { padding: 9px 12px; border-radius: 6px; background: #121212; font-size: 0.85rem; color: #d4d4d4; border-left: 3px solid #737373; cursor: pointer; transition: 0.2s; }
        .project-item:hover { background: #1c1c1c; border-left-color: #ffffff; color: #ffffff; }
        .quick-btn { padding: 8px 10px; border-radius: 6px; background: #121212; border: 1px solid #222222; color: #a3a3a3; font-size: 0.8rem; text-align: left; cursor: pointer; margin-bottom: 6px; transition: 0.2s; }
        .quick-btn:hover { border-color: #525252; color: #ffffff; background: #171717; }
        .system-status { margin-top: auto; background: #0a0a0a; padding: 14px; border-radius: 10px; font-size: 0.78rem; border: 1px solid #222222; }
        .status-row { display: flex; justify-content: space-between; margin-bottom: 6px; color: #737373; }
        .status-row:last-child { margin-bottom: 0; }
        .badge-ok { color: #ffffff; font-weight: 600; }
        .main { flex: 1; display: flex; flex-direction: column; background: #000000; }
        .header { height: 66px; background: #0a0a0a; border-bottom: 1px solid #222222; display: flex; align-items: center; justify-content: space-between; padding: 0 24px; padding-bottom: 0.3rem; }
        .header-title { display: flex; flex-direction: column; }
        .header-title strong { font-size: 0.98rem; color: #ffffff; }
        .header-title span { font-size: 0.74rem; color: #737373; }
        .header-right { display: flex; align-items: center; gap: 10px; }
        .tool-btn { background: #171717; color: #d4d4d4; border: 1px solid #333333; padding: 7px 12px; border-radius: 8px; font-size: 0.78rem; font-weight: 600; cursor: pointer; transition: 0.2s; }
        .tool-btn:hover { background: #262626; color: #ffffff; border-color: #525252; }
        .telemetry { display: flex; gap: 14px; font-size: 0.78rem; color: #a3a3a3; background: #121212; padding: 8px 14px; border-radius: 20px; border: 1px solid #222222; }
        .telemetry b { color: #ffffff; font-family: Consolas, monospace; }
        .chat-container { flex: 1; padding: 28px; overflow-y: auto; display: flex; flex-direction: column; gap: 20px; scroll-behavior: smooth; }
        .message { display: flex; gap: 14px; max-width: 84%; line-height: 1.65; font-size: 0.95rem; }
        .message.user { align-self: flex-end; flex-direction: row-reverse; }
        .avatar { width: 40px; height: 40px; border-radius: 10px; display: flex; align-items: center; justify-content: center; font-size: 1.25rem; flex-shrink: 0; }
        .usta .avatar { background: #171717; border: 1px solid #404040; color: #ffffff; }
        .user .avatar { background: #262626; border: 1px solid #525252; color: #ffffff; }
        .bubble { padding: 14px 18px; border-radius: 14px; background: #121212; border: 1px solid #262626; color: #e5e5e5; overflow-x: auto; }
        .user .bubble { background: #262626; border-color: #404040; color: #ffffff; }
        .bubble p { margin-bottom: 10px; }
        .bubble p:last-child { margin-bottom: 0; }
        .bubble ul, .bubble ol { margin-left: 22px; margin-bottom: 10px; }
        .bubble code { background: #0a0a0a; padding: 2px 6px; border-radius: 4px; color: #ffffff; font-family: Consolas, monospace; font-size: 0.9em; border: 1px solid #222222; }
        .bubble pre { position: relative; margin-top: 10px; margin-bottom: 10px; }
        .bubble pre code { display: block; padding: 14px; border-radius: 8px; overflow-x: auto; color: #e5e5e5; background: #080808; border: 1px solid #222222; }
        .copy-btn { position: absolute; top: 8px; right: 8px; background: #222222; color: #a3a3a3; border: 1px solid #333333; padding: 4px 10px; border-radius: 4px; font-size: 0.75rem; cursor: pointer; }
        .copy-btn:hover { background: #333333; color: #ffffff; }
        .stopped-tag { display: inline-block; margin-top: 8px; font-size: 0.75rem; color: #a3a3a3; background: #1a1a1a; border: 1px solid #333333; padding: 3px 8px; border-radius: 4px; }
        .input-area { padding: 18px 28px; background: #0a0a0a; border-top: 1px solid #222222; display: flex; gap: 12px;border-radius: 1rem 1rem 0 0; }
        .input-area input { flex: 1; background: #121212; border: 1px solid #262626; color: #ffffff; padding: 14px 18px; border-radius: 10px; font-size: 0.95rem; outline: none; transition: 0.2s; }
        .input-area input:focus { border-color: #737373; background: #171717; }
        .send-btn { background: #ffffff; color: #000000; border: 1px solid #ffffff; padding: 0 28px; border-radius: 10px; font-weight: 700; cursor: pointer; transition: 0.2s; font-size: 0.95rem; min-width: 130px; }
        .send-btn:hover { background: #d4d4d4; }
        .send-btn.stop-mode { background: #171717; color: #f87171; border: 1px solid #dc2626; }
        .send-btn.stop-mode:hover { background: #dc2626; color: #ffffff; }
    </style>
</head>
<body>
    <div class="sidebar">
        <div class="logo">
            <span>⬛ LOCAL AI</span>
            <span class="logo-badge">ON-PREMISE</span>
        </div>
        <button class="btn-action" onclick="hafizaTemizle()">🗑️ SQL Hafızasını Sıfırla</button>
        <button class="btn-schema" onclick="hazirSor('Canlı SQL veritabanı şemasını analiz et')">🔍 Canlı SQL Şema Denetimi</button>
        
        <div class="section-title">Hızlı Senaryo Testleri</div>
        <button class="quick-btn" onclick="hazirSor('Usta selam!')">👋 Selam Ver (İzolasyon Testi)</button>
        <button class="quick-btn" onclick="hazirSor('SQL\'de deadlock yaşıyorum ne yapmalıyım?')">⚡ SQL Deadlock Analizi</button>
        <button class="quick-btn" onclick="hazirSor('C# projesinde bellek sızıntısı için ne yapmalıyım?')">🛠️ C# Bellek Sızıntısı (GC)</button>

        <div class="section-title">Proje Klasörü (Hibrit Code Review)</div>
        <div class="project-list" id="projectList">
            <div class="project-item">Yükleniyor...</div>
        </div>
        
        <div class="system-status">
            <div class="status-row"><span>Model:</span> <span class="badge-ok" id="modelName">gemma2:9b</span></div>
            <div class="status-row"><span>Mimari:</span> <span class="badge-ok">Statik + LLM</span></div>
            <div class="status-row"><span>Veri Gizliliği:</span> <span class="badge-ok">%100 Yerel 🔒</span></div>
        </div>
    </div>

    <div class="main">
        <div class="header">
            <div class="header-title">
                <strong>Usta — Hibrit Yazılım ve Veritabanı Denetçisi</strong>
                <span>Statik AST/Regex Ön-Analiz + Yerel LLM + Canlı SQL Şema Motoru</span>
            </div>
            <div class="header-right">
                <button class="tool-btn" onclick="raporIndir()">📥 Rapor İndir (.md)</button>
                <button class="tool-btn" onclick="ekraniTemizle()">🧹 Ekranı Temizle</button>
                <div class="telemetry">
                    <span>İlk Token (TTFT): <b id="ttft">Hazır</b></span>
                    <span>Hız: <b id="tps">0.0 token/sn</b></span>
                    <span>Toplam: <b id="latency">0 ms</b></span>
                </div>
            </div>
        </div>

        <div class="chat-container" id="chatBox"></div>

        <div class="input-area">
            <input type="text" id="userInput" placeholder="Bir proje seç, SQL şemasını denetle veya teknik bir soru sor..." onkeypress="if(event.key==='Enter') butonaBasildi()">
            <button class="send-btn" id="sendBtn" onclick="butonaBasildi()">Gönder</button>
        </div>
    </div>

    <script>
        const chatBox = document.getElementById('chatBox');
        const userInput = document.getElementById('userInput');
        const sendBtn = document.getElementById('sendBtn');
        const latencyEl = document.getElementById('latency');
        const ttftEl = document.getElementById('ttft');
        const tpsEl = document.getElementById('tps');

        let abortController = null;
        let uretimAktif = false;
        let oturumKayitlari = [];

        function guvenliFormatla(metin) {
            if (typeof marked !== 'undefined' && marked.parse) {
                return marked.parse(metin);
            }
            return metin.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/\n/g, '<br>');
        }

        function kodRenklendirVeKopyala(container) {
            if (typeof hljs !== 'undefined') {
                container.querySelectorAll('pre code').forEach(el => hljs.highlightElement(el));
            }
            container.querySelectorAll('pre').forEach(pre => {
                if (pre.querySelector('.copy-btn')) return;
                const btn = document.createElement('button');
                btn.className = 'copy-btn';
                btn.innerText = 'Kopyala';
                btn.onclick = () => {
                    const code = pre.querySelector('code')?.innerText || '';
                    navigator.clipboard.writeText(code);
                    btn.innerText = 'Kopyalandı ✓';
                    setTimeout(() => btn.innerText = 'Kopyala', 1500);
                };
                pre.appendChild(btn);
            });
        }

        function mesajBalonuOlustur(kim, metin = '') {
            const msgDiv = document.createElement('div');
            msgDiv.className = `message ${kim}`;
            const ikon = kim === 'usta' ? '⬛' : '👤';
            const icerik = kim === 'usta' ? guvenliFormatla(metin) : metin;

            msgDiv.innerHTML = `<div class="avatar">${ikon}</div><div class="bubble">${icerik}</div>`;
            chatBox.appendChild(msgDiv);
            chatBox.scrollTop = chatBox.scrollHeight;
            
            const bubble = msgDiv.querySelector('.bubble');
            kodRenklendirVeKopyala(bubble);
            return bubble;
        }

        async function baslangicYukle() {
            try {
                const res = await fetch('/status');
                const data = await res.json();
                document.getElementById('modelName').innerText = data.model;
                
                const pList = document.getElementById('projectList');
                pList.innerHTML = '';
                if (!data.projects || data.projects.length === 0) {
                    pList.innerHTML = '<div class="project-item" style="border-color:#525252">Klasörde proje yok</div>';
                } else {
                    data.projects.forEach(p => {
                        const item = document.createElement('div');
                        item.className = 'project-item';
                        item.innerText = '📁 ' + p;
                        item.onclick = () => hazirOrdCodeReview(p);
                        pList.appendChild(item);
                    });
                }

                if (!data.history || data.history.length === 0) {
                    mesajBalonuOlustur('usta', 'Selam evlat! Hibrit Statik Analiz + Yerel LLM motorumuz ve Canlı SQL Şema Denetçimiz hazır. Hangi projeyi veya tabloyu inceliyoruz? ⬛');
                } else {
                    data.history.forEach(m => {
                        mesajBalonuOlustur(m.role === 'user' ? 'user' : 'usta', m.content);
                        oturumKayitlari.push({ role: m.role, content: m.content });
                    });
                }
            } catch (e) {
                mesajBalonuOlustur('usta', 'Sunucu bağlantısı kuruldu evlat, sorabilirsin! ⬛');
            }
        }

        function hazirSor(metin) {
            if (uretimAktif) return;
            userInput.value = metin;
            gonder();
        }

        function hazirOrdCodeReview(projeAdi) {
            if (uretimAktif) return;
            userInput.value = `${projeAdi} projesini code review yap ve hataları incele`;
            gonder();
        }

        function ekraniTemizle() {
            if (uretimAktif && abortController) abortController.abort();
            chatBox.innerHTML = '';
            mesajBalonuOlustur('usta', 'Ekranı temizledim evlat, SQL hafızamız yerinde duruyor. Devam edebiliriz! ⬛');
        }

        async function hafizaTemizle() {
            if (uretimAktif && abortController) abortController.abort();
            const res = await fetch('/clear', { method: 'POST' });
            const data = await res.json();
            chatBox.innerHTML = '';
            oturumKayitlari = [];
            mesajBalonuOlustur('usta', data.message);
        }

        function raporIndir() {
            if (oturumKayitlari.length === 0) {
                alert("İndirilecek analiz kaydı bulunamadı.");
                return;
            }
            let md = "# LOCAL AI — Teknik Denetim ve Analiz Raporu\n";
            md += `- **Model:** ${document.getElementById('modelName').innerText}\n`;
            md += `- **Son TTFT:** ${ttftEl.innerText} | **Hız:** ${tpsEl.innerText} | **Toplam Süre:** ${latencyEl.innerText}\n\n---\n\n`;
            oturumKayitlari.forEach(k => {
                const baslik = k.role === 'user' ? '### 👤 Geliştirici İstemi' : '### ⬛ Usta (Hibrit Denetim Yanıtı)';
                md += `${baslik}\n\n${k.content}\n\n---\n\n`;
            });
            const blob = new Blob([md], { type: "text/markdown;charset=utf-8" });
            const url = URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url;
            a.download = "LocalAI_Denetim_Raporu.md";
            a.click();
            URL.revokeObjectURL(url);
        }

        function butonaBasildi() {
            if (uretimAktif) {
                if (abortController) abortController.abort();
            } else {
                gonder();
            }
        }

        function butonDurumuAyarla(aktifMi) {
            uretimAktif = aktifMi;
            if (aktifMi) {
                sendBtn.innerText = '⏹ Durdur';
                sendBtn.classList.add('stop-mode');
            } else {
                sendBtn.innerText = 'Gönder';
                sendBtn.classList.remove('stop-mode');
            }
        }

        async function gonder() {
            const soru = userInput.value.trim();
            if (!soru || uretimAktif) return;

            userInput.value = '';
            butonDurumuAyarla(true);
            mesajBalonuOlustur('user', soru);
            oturumKayitlari.push({ role: 'user', content: soru });

            const ustaBubble = mesajBalonuOlustur('usta', '*Ön analiz ve model çıkarımı yapılıyor...* ⬛');
            const baslangic = performance.now();
            let ilkTokenGeldi = false;

            ttftEl.innerText = 'Ölçülüyor...';
            latencyEl.innerText = '...';
            tpsEl.innerText = '0.0 token/sn';

            abortController = new AbortController();
            let tamMetin = '';
            let parcaSayisi = 0;

            try {
                const response = await fetch('/ask', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ question: soru }),
                    signal: abortController.signal
                });

                const reader = response.body.getReader();
                const decoder = new TextDecoder('utf-8');

                while (true) {
                    const { done, value } = await reader.read();
                    if (done) break;
                    
                    if (!ilkTokenGeldi) {
                        ilkTokenGeldi = true;
                        ttftEl.innerText = Math.round(performance.now() - baslangic) + ' ms';
                    }

                    const yeniMetin = decoder.decode(value, { stream: true });
                    tamMetin += yeniMetin;
                    parcaSayisi++;

                    const gecenMs = performance.now() - baslangic;
                    const gecenSn = gecenMs / 1000;
                    const tahminiToken = Math.max(parcaSayisi, Math.ceil(tamMetin.length / 4));
                    
                    if (gecenSn > 0.1) {
                        tpsEl.innerText = (tahminiToken / gecenSn).toFixed(1) + ' token/sn';
                        latencyEl.innerText = Math.round(gecenMs) + ' ms';
                    }

                    ustaBubble.innerHTML = guvenliFormatla(tamMetin);
                    chatBox.scrollTop = chatBox.scrollHeight;
                }

                const toplamSure = Math.round(performance.now() - baslangic);
                latencyEl.innerText = toplamSure + ' ms ⚡';
                if (tamMetin.trim()) {
                    oturumKayitlari.push({ role: 'assistant', content: tamMetin });
                }
            } catch (err) {
                if (err.name === 'AbortError') {
                    const durdurmaNotu = '<div class="stopped-tag">⏹ Yanıt durduruldu</div>';
                    ustaBubble.innerHTML = (tamMetin ? guvenliFormatla(tamMetin) : '') + durdurmaNotu;
                    const kesilenSure = Math.round(performance.now() - baslangic);
                    latencyEl.innerText = kesilenSure + ' ms (Durduruldu)';
                } else {
                    ustaBubble.innerHTML = `<span style="color:#ef4444">Bağlantı Hatası: ${err.message}</span>`;
                }
            } finally {
                kodRenklendirVeKopyala(ustaBubble);
                butonDurumuAyarla(false);
                abortController = null;
                userInput.focus();
            }
        }

        window.onload = baslangicYukle;
    </script>
</body>
</html>
"""

HTML_ARAYUZ = (
    HTML_ARAYUZ
    .replace("__CDN_MARKED__", CDN_MARKED)
    .replace("__CDN_HLJS_CSS__", CDN_HLJS_CSS)
    .replace("__CDN_HLJS_JS__", CDN_HLJS_JS)
)

class AskRequest(BaseModel):
    question: str

@app.get("/", response_class=HTMLResponse)
def serve_ui():
    return HTML_ARAYUZ

@app.get("/status")
def get_status():
    return JSONResponse({
        "model": LOCAL_MODEL,
        "projects": list_projects(),
        "history": load_messages(limit=8)
    })

@app.post("/clear")
def clear_endpoint():
    msg = clear_memory()
    return JSONResponse({"message": msg})

@app.post("/ask")
def ask_endpoint(req: AskRequest):
    return StreamingResponse(generate_ai_chunks(req.question), media_type="text/plain; charset=utf-8")

def tarayiciyi_ac():
    time.sleep(1.5)
    os.system(f'start msedge --app="{LOCAL_URL}"')

if __name__ == "__main__":
    print("=" * 60)
    print(f"LOCAL AI STUDIO AKTİF (Model: {LOCAL_MODEL})")
    print(f"Arayüz Adresi: {LOCAL_URL}")
    print("SQL Server: DESKTOP-MB05P67 -> LocalAI -> dbo.Cons")
    print("=" * 60)
    threading.Thread(target=tarayiciyi_ac, daemon=True).start()
    uvicorn.run(app, host="127.0.0.1", port=PORT)
