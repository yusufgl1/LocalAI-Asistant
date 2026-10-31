# ⬛ LOCAL AI — Veri Mahremiyeti Odaklı Hibrit Kod ve Veritabanı Şema Denetim Sistemi

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white)
![Ollama](https://img.shields.io/badge/Ollama-Gemma2:9B-000000?style=for-the-badge)
![MS SQL Server](https://img.shields.io/badge/MS_SQL_Server-CC2927?style=for-the-badge&logo=microsoft-sql-server&logoColor=white)
![Architecture](https://img.shields.io/badge/Architecture-On--Premise_%2F_Air--Gapped-success?style=for-the-badge)

Kurumsal kaynak kodların ve veritabanı şemalarının bulut tabanlı Büyük Dil Modellerine (LLM) gönderilmesi, Fikri Mülkiyet ve KVKK açısından ciddi veri sızıntısı riskleri taşır[cite: 3]. Ayrıca yalnızca saf dil modellerine dayalı kod incelemelerinde, modelin projede bulunmayan kütüphaneleri varsayması (**halüsinasyon**) ve sistem yönergelerini çıktıya sızdırması (**prompt leakage**) gibi güvenilirlik sorunları yaşanmaktadır[cite: 3].

**LOCAL AI**, dış ağ bağlantısına ihtiyaç duymadan tamamen yerel donanım kaynakları (**%100 Yerel / On-Premise / Air-Gapped**) üzerinde çalışan[cite: 3]; **C# (.NET)** projelerini ve **MS SQL Server** veritabanı mimarilerini gerçek zamanlı denetleyen **kural + yapay zekâ hibriti** bir geliştirici stüdyosudur[cite: 3].

---

## 🚀 Temel Özellikler ve 4 Fazlı Yöntem

Sistem, standart bir LLM arayüzü yerine **4 ardışık mühendislik fazından** oluşan özgün bir mimariyle çalışır[cite: 3]:

### 01. Niyet Sınıflandırma ve Dinamik Bağlam İzolasyonu
Kullanıcı istemleri doğrudan modele gönderilmez; önce karar mekanizmasıyla sınıflandırılır[cite: 3]. Yalnızca ilgili teknik bağlam çalışma zamanında dinamik olarak enjekte edilir ve **KV-Cache** her sorguda sıfırlanarak görevler arası bağlam sızıntısı (prompt leakage) engellenir[cite: 3].

### 02. Nöro-Sembolik Kod Denetimi (Önce Kural, Sonra Model)
Kaynak kodlar `Gemma-2 9B` modeline aktarılmadan önce deterministik statik analiz motorundan geçirilir[cite: 3]. Tespit edilen kesin bulgular **RAG (Retrieval-Augmented Generation)** kanıtı olarak modele sunulur ve halüsinasyon kanıtla sınırlanır[cite: 3]:
* **`IDisposable` İhlalleri:** `using` bloğu veya `.Dispose()` çağrısı bulunmayan nesnelerden kaynaklı bağlantı havuzu (*Connection Pool*) sızıntıları[cite: 3].
* **`int.Parse` Kullanımı:** Doğrudan tip dönüşümlerinde `TryParse` eksikliğinden kaynaklanan `FormatException` çökme riskleri[cite: 3].
* **`SQL Injection`:** Metin birleştirme (`+`) ile oluşturulan parametresiz sorguların doğurduğu veri manipülasyonu ve yetkisiz erişim riskleri[cite: 3].

### 03. Canlı SQL Server Katalog Çıkarımı
Veritabanı denetçisi statik betikleri okumak yerine doğrudan çalışan MS SQL Server örneğine bağlanarak `sys.tables`, `sys.columns` ve `sys.indexes` sistem kataloglarını `WITH (NOLOCK)` izolasyonuyla canlı sorgular[cite: 3]:
* **Primary Key** eksikliği bulunan (*Heap*) tabloları[cite: 3],
* Veri tipi ve bellek boyutu uyumsuzluklarını[cite: 3],
* Tablo bazlı aktif indeks durumlarını otomatik raporlar[cite: 3].

### 04. VRAM Koruma ve Akış Telemetrisi
Model ağırlıkları `keep_alive="15m"` parametresiyle VRAM üzerinde 15 dakika sıcak tutulurken `Temperature: 0.1` ile deterministiğe yakın çıkarım yapılır[cite: 3]. Üretilen her yanıt için[cite: 3]:
* **TTFT (Time-To-First-Token):** İlk token üretim süresi (ms)[cite: 3],
* **TPS (Tokens Per Second):** Saniyedeki token üretim hızı[cite: 3],
* **Latency:** Toplam uçtan uca gecikme süresi anlık olarak hesaplanır ve tek tıkla `.md` formatında denetim raporu olarak dışa aktarılır[cite: 3].

---

## 🏗️ Sistem Mimarisi

```text
+-----------------------------------------------------------------------------------+
|                        1. SUNUM VE TELEMETRİ KATMANI (Web UI)                     |
|   [Proje Seçici & Hızlı Testler]  |  [TTFT / TPS Ölçer]  |  [MD Rapor Dışa Aktar] |
+-----------------------------------+----------------------+------------------------+
                                    |  HTTP POST /ask (Streaming)
                                    v
+-----------------------------------------------------------------------------------+
|                   2. ORKESTRASYON VE İZOLASYON KATMANI (FastAPI)                  |
|                        [Niyet Sınıflandırıcı (Intent Router)]                     |
|                                   |                                               |
|        +--------------------------+--------------------------+                    |
|        | (Code Review)            | (SQL Şema Analizi)       | (Teknik Sorgu)     |
|        v                          v                          v                    |
|  [Statik Ön-Analiz Motoru]  [Canlı Katalog Denetçisi]  [Dinamik Kural Enjektörü]  |
|  (IDisposable, Parse, SQLi) (sys.tables / sys.indexes) (Deadlock / RCSI / CS0246) |
+--------+--------------------------+--------------------------+--------------------+
         |                          |                          |
         +--------------------------+--------------------------+
                                    |  Deterministik Ön-Analiz Kanıtı (RAG)
                                    v
+-----------------------------------------------------------------------------------+
|               3. YEREL ÇIKARIM VE VERİ KALICILIĞI KATMANI (On-Premise)            |
|   +---------------------------------------+   +-------------------------------+   |
|   | Ollama Yerel Çıkarım Motoru           |   | MS SQL Server (LocalAI DB)    |   |
|   | Model: Gemma-2 (9B) | Temp: 0.1       |   | Tablo: dbo.Cons               |   |
|   | VRAM Keep-Alive: 15m | Sıfır KV-Cache |   | İşlem: Diyalog & Log Kaydı    |   |
|   +---------------------------------------+   +-------------------------------+   |
+-----------------------------------------------------------------------------------+
```

---

## 📊 Neden Hibrit Sistem?

| Kriter | Bulut LLM'ler | Saf Yerel LLM | **LOCAL AI (Hibrit Sistem)** |
| :--- | :---: | :---: | :---: |
| **Veri Gizliliği (KVKK / IP)** | Riskli | Güvenli | **Tam Güvenli (%100 Yerel)**[cite: 3] |
| **Halüsinasyon Oranı** | Orta | Yüksek | **Minimum (Statik Kanıt Destekli)**[cite: 3] |
| **Canlı SQL Şema Erişimi** | Yok | Yok | **Tam Entegre (`sys.*` Katalogları)**[cite: 3] |
| **Prompt Sızıntısı Direnci** | Yüksek | Düşük | **Yüksek (Dinamik İzolasyon)**[cite: 3] |
| **Akademik Ölçülebilirlik** | Yok | Yok | **TTFT, TPS ve Latency Telemetrisi**[cite: 3] |

> **Test Ortamı Telemetri Sonucu:** Model VRAM üzerinde sıcak tutulurken yapılan canlı testlerde **İlk Token Süresi (TTFT) `991 ms`**, üretim hızı **`7.3 token/sn`** ve toplam yanıt süresi **`5922 ms`** olarak ölçülmüştür[cite: 3].

---

## ⚙️ Kurulum ve Çalıştırma

### 1. Gereksinimler
* **Python 3.10+**
* **Ollama** (Yerel LLM motoru)[cite: 3]
* **Microsoft SQL Server** ve **ODBC Driver 17 for SQL Server**

### 2. Yerel Modelin İndirilmesi
Terminal üzerinden `gemma2:9b` modelini yerel makinenize çekin:
```bash
ollama pull gemma2:9b
```

### 3. Veritabanı Tablosunun Oluşturulması
MS SQL Server üzerinde `LocalAI` adında bir veritabanı oluşturun ve aşağıdaki T-SQL betiğini çalıştırın:
```sql
CREATE DATABASE LocalAI;
GO
USE LocalAI;
GO
CREATE TABLE dbo.Cons (
    Id INT IDENTITY(1,1) PRIMARY KEY,
    Role NVARCHAR(50) NOT NULL,
    MessagesSent NVARCHAR(MAX) NOT NULL,
    Tarih DATETIME DEFAULT GETDATE()
);
GO
```

### 4. Kütüphanelerin Kurulumu ve Başlatma
```bash
pip install fastapi uvicorn ollama pyodbc pydantic
```

Kod içerisindeki `SQL_CONN_STR` bağlantı dizesini kendi SQL Server örneğinize (`SERVER=LOCALHOST\SQLEXPRESS;`) göre ve `PROJECT_ROOT` dizinini incelenecek projelerinizin bulunduğu klasöre göre güncelledikten sonra uygulamayı başlatın:
```bash
python main.py
```
Uygulama otomatik olarak `http://127.0.0.1:8080` adresinde Geliştirici Stüdyosu arayüzünü başlatacaktır.

## 👤 Geliştirici
**Muhammed Yusuf Gül**

---
---

# ⬛ LOCAL AI — Privacy-First Hybrid Code & Database Schema Auditing System

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white)
![Ollama](https://img.shields.io/badge/Ollama-Gemma2:9B-000000?style=for-the-badge)
![MS SQL Server](https://img.shields.io/badge/MS_SQL_Server-CC2927?style=for-the-badge&logo=microsoft-sql-server&logoColor=white)
![Architecture](https://img.shields.io/badge/Architecture-On--Premise_%2F_Air--Gapped-success?style=for-the-badge)

Sending enterprise source code and database schemas to cloud-based Large Language Models (LLMs) poses severe Intellectual Property (IP) and data privacy risks[cite: 3]. Furthermore, relying solely on probabilistic LLMs for code reviews often leads to **hallucinations** (assuming non-existent libraries in the project) and **prompt leakage** (exposing system instructions in the output)[cite: 3].

**LOCAL AI** is a **100% On-Premise / Air-Gapped** hybrid developer studio that operates entirely on local hardware without an external internet connection[cite: 3]; it combines **deterministic static rules** with **artificial intelligence** to audit **C# (.NET)** projects and **MS SQL Server** database architectures in real time[cite: 3].

---

## 🚀 Key Features & Four-Phase Methodology

Instead of a standard LLM wrapper, the system operates on a novel architecture consisting of **4 sequential engineering phases**[cite: 3]:

### 01. Intent Classification & Dynamic Context Isolation
User prompts are not sent directly to the model; they are first classified by a routing mechanism[cite: 3]. Only the relevant technical context is dynamically injected at runtime, and the **KV-Cache** is flushed on every query to prevent cross-task context contamination (prompt leakage)[cite: 3].

### 02. Neuro-Symbolic Code Auditing (Rule First, Model Second)
Before source code is passed to the `Gemma-2 9B` model, it is scanned by a deterministic static pre-analysis engine[cite: 3]. Verified findings are fed into the model as **RAG (Retrieval-Augmented Generation)** evidence, bounding hallucinations with hard proof[cite: 3]:
* **`IDisposable` Violations:** Connection pool leaks caused by objects missing `using` blocks or `.Dispose()` calls[cite: 3].
* **`int.Parse` Usage:** Runtime `FormatException` crash risks resulting from direct type conversions without `TryParse`[cite: 3].
* **`SQL Injection`:** Data manipulation and unauthorized access risks caused by unparameterized string-concatenated (`+`) queries[cite: 3].

### 03. Live SQL Server Catalog Introspection
Rather than reading static SQL scripts, the database auditor connects directly to the active MS SQL Server instance and queries the `sys.tables`, `sys.columns`, and `sys.indexes` system catalogs live using `WITH (NOLOCK)` isolation[cite: 3]:
* Automatically reports **Heap tables** missing a **Primary Key**[cite: 3],
* Data type and memory allocation mismatches[cite: 3],
* Active index statuses per table[cite: 3].

### 04. VRAM Retention & Streaming Telemetry
While model weights are kept warm in VRAM for 15 minutes via `keep_alive="15m"`, near-deterministic inference is performed at `Temperature: 0.1`[cite: 3]. For every generated response[cite: 3]:
* **TTFT (Time-To-First-Token):** First token generation latency (ms)[cite: 3],
* **TPS (Tokens Per Second):** Real-time token generation speed[cite: 3],
* **Latency:** Total end-to-end response time is calculated on the fly and can be exported as a `.md` audit report with a single click[cite: 3].

---

## 🏗️ System Architecture

```text
+-----------------------------------------------------------------------------------+
|                        1. PRESENTATION & TELEMETRY LAYER (Web UI)                 |
|   [Project Selector & Quick Tests]  |  [TTFT / TPS Meter]  |  [MD Report Export]  |
+-------------------------------------+----------------------+----------------------+
                                      |  HTTP POST /ask (Streaming)
                                      v
+-----------------------------------------------------------------------------------+
|                   2. ORCHESTRATION & ISOLATION LAYER (FastAPI)                    |
|                          [Intent Classifier & Router]                             |
|                                     |                                             |
|        +----------------------------+----------------------------+                |
|        | (Code Review)              | (SQL Schema Audit)         | (Tech Query)   |
|        v                            v                            v                |
|  [Static Pre-Analysis Engine] [Live Catalog Inspector]   [Dynamic Rule Injector]  |
|  (IDisposable, Parse, SQLi)   (sys.tables / sys.indexes) (Deadlock / RCSI / CS0246)|
+--------+----------------------------+----------------------------+----------------+
         |                            |                            |
         +----------------------------+----------------------------+
                                      |  Deterministic Pre-Analysis Evidence (RAG)
                                      v
+-----------------------------------------------------------------------------------+
|               3. LOCAL INFERENCE & PERSISTENCE LAYER (On-Premise)                 |
|   +---------------------------------------+   +-------------------------------+   |
|   | Ollama Local Inference Engine         |   | MS SQL Server (LocalAI DB)    |   |
|   | Model: Gemma-2 (9B) | Temp: 0.1       |   | Table: dbo.Cons               |   |
|   | VRAM Keep-Alive: 15m | Zero KV-Cache  |   | Task: Dialogue & Audit Logs   |   |
|   +---------------------------------------+   +-------------------------------+   |
+-----------------------------------------------------------------------------------+
```

---

## 📊 Why Hybrid Architecture?

| Evaluation Metric | Cloud LLMs | Pure Local LLM | **LOCAL AI (Hybrid System)** |
| :--- | :---: | :---: | :---: |
| **Data Privacy (GDPR / KVKK / IP)** | Risky | Secure | **Fully Secure (100% Local)**[cite: 3] |
| **Hallucination Rate** | Medium | High | **Minimal (Grounded by Static Evidence)**[cite: 3] |
| **Live SQL Schema Access** | None | None | **Fully Integrated (`sys.*` Catalogs)**[cite: 3] |
| **Prompt Leakage Resistance** | High | Low | **High (Dynamic Isolation)**[cite: 3] |
| **Academic Observability** | None | None | **TTFT, TPS & Latency Telemetry**[cite: 3] |

> **Benchmark Telemetry Result:** During live tests with model weights kept warm in VRAM, **Time-To-First-Token (TTFT) was measured at `991 ms`**, generation speed at **`7.3 tokens/sec`**, and total response latency at **`5922 ms`**[cite: 3].

---

## ⚙️ Installation & Execution

### 1. Prerequisites
* **Python 3.10+**
* **Ollama** (Local LLM engine)[cite: 3]
* **Microsoft SQL Server** and **ODBC Driver 17 for SQL Server**

### 2. Pulling the Local Model
Download the `gemma2:9b` model to your local machine via terminal:
```bash
ollama pull gemma2:9b
```

### 3. Creating the Database Table
Create a database named `LocalAI` on MS SQL Server and execute the following T-SQL script:
```sql
CREATE DATABASE LocalAI;
GO
USE LocalAI;
GO
CREATE TABLE dbo.Cons (
    Id INT IDENTITY(1,1) PRIMARY KEY,
    Role NVARCHAR(50) NOT NULL,
    MessagesSent NVARCHAR(MAX) NOT NULL,
    Tarih DATETIME DEFAULT GETDATE()
);
GO
```

### 4. Installing Dependencies & Running
```bash
pip install fastapi uvicorn ollama pyodbc pydantic
```

Update the `SQL_CONN_STR` connection string in the code according to your SQL Server instance (`SERVER=LOCALHOST\SQLEXPRESS;`) and `PROJECT_ROOT` to the directory containing the projects you want to audit, then launch the application:
```bash
python main.py
```
The application will automatically launch the Developer Studio interface at `http://127.0.0.1:8080`.

## 👤 Developer
**Muhammed Yusuf Gül**
