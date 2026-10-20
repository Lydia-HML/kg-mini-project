# KG Mini Project — 修課知識圖譜（RDF ＋ Property Graph）

對應《Knowledge Graph Fundamentals》2026 本週講義第 23 頁 Mini Project：
以**同一份 CSV** 交付兩種資料模型的小型 KG，附 ontology、查詢、SHACL 驗證與自動測試。

## 快速開始

```bash
pip install -r requirements.txt
python build_kg.py     # 建圖、查詢、推論、驗證，產出 out/
pytest -v              # 22 項測試（依評分面向分組，含反例）
```

## 檔案

| 檔案 | 內容 | 講義頁 |
|---|---|---|
| `data/*.csv` | 學生、課程、修課、授課、主張（刻意含髒資料） | 16 |
| `ontology.ttl` | TBox：Student／GraduateStudent／Teacher／Course、enrolledIn、EnrollmentClaim | 14–15、21 |
| `shapes.ttl` | SHACL：姓名須為 literal、enrolledIn 起訖型別、來源必填 | 21–22 |
| `build_kg.py` | CSV→RDF、CSV→LPG、CSV→Cypher、SPARQL、RDFS 推論、SHACL | 16、19–21 |
| `test_kg.py` | 依評分規準 40/25/20/15 組織的測試 | 22–23 |
| `concept_map.dot` | 10 節點概念圖原始檔 | 23 |
| `out/kg.ttl` | 產出的 Turtle（ABox） | 20 |
| `out/load.cypher` | 可在 Neo4j 執行的匯入＋驗證＋查詢腳本 | 19 |
| `out/mapping_report.json` | 被拒／重複的資料列與筆數 | 16、18 |
| `out/concept_map.png/.svg` | 概念圖 | 23 |

## 繳交物對照（第 23 頁）

| 要求 | 本專案 |
|---|---|
| 5–10 節點概念圖 | `out/concept_map.png`：類別層 4 ＋ 個體層 6 ＝ 10 |
| 五筆 RDF triples | `out/kg.ttl` 共 50+ 筆；最小五筆：`S01 a Student`、`S02 a Student`、`C01 a Course`、`S01 enrolledIn C01`、`S02 enrolledIn C01` |
| ≥3 LPG 節點、2 關係 | S01、S02、C01 ＋ 兩條 `ENROLLED_IN {semester}` |
| 簡要 ontology | `ontology.ttl` |
| 兩條查詢 | SPARQL 與 Cypher「選 C01 的學生」→ S01 Mei、S02 Hua |

## CSV → KG Mapping（第 16 頁）

| 來源欄位 | 目標 | 轉換規則 |
|---|---|---|
| `students.student_no` | `Student.id` / `ex:{id}` | trim 空白、驗證唯一 |
| `students.name` | `ex:name` / `s.name` | `"…"@en` 語言標記 literal |
| `students.level` | `rdf:type` / 額外 label | `graduate` → `GraduateStudent` |
| `courses.course_code` | `Course.id` / `ex:{id}` | 以穩定 ID 去重 |
| `enrollment(student_no, course_code, semester)` | `ex:enrolledIn` ＋ `ex:Enrollment` 事件節點；LPG：`[:ENROLLED_IN {semester}]` | 無法對應 ID、空值 → 拒收並記錄；同學期同課 → 視為重複 |
| `enrollment.recorded_on` ＋ 列號 | `ex:recordedOn`、`ex:sourceFile`、`ex:sourceRow` | 可逐筆追回原始列 |
| `claims.csv` | `ex:EnrollmentClaim {status, source}` | **不**升級為 `enrolledIn` |

本次資料清理結果：拒收 2 列（學號 S09 不存在、course_code 空白）、重複 1 列，皆寫入 `mapping_report.json`。

## 建置過程中踩到的兩個坑（都正好是講義重點）

**1. `rdfs:domain` 會「推論」，不會「拒絕」（第 21 頁）**
第一版把 `ex:student` 的 domain 設為 `ex:Enrollment`。結果 RDFS 推論把兩筆「未確認的修課主張」全推成確定的 `Enrollment`。修法：被多種類別共用的屬性不宣告 domain。`test_claims_not_inferred_as_enrollment` 防止回歸。

**2. 先推論再驗證，錯誤會被「洗白」（第 21 頁、解答本第 21 頁）**
SHACL 若以 `inference="rdfs"` 執行，`ex:S01 ex:enrolledIn ex:T01`（物件是老師）會先因 `rdfs:range ex:Course` 被推成 `T01 a Course`，`sh:class` 檢查就通過了。修法：對原始資料驗證（`inference="none"`），並用 `sh:targetSubjectsOf ex:enrolledIn` 檢查方向。

## 衝突證據的處理（第 23 頁延伸討論）

S03 是否修 C01 有兩個來源：LLM 從會議紀錄擷取（`unverified`）與教務處匯出（`refuted`）。
兩筆都保留為 `EnrollmentClaim`，各自帶 `status`、`source`、`recordedOn`；**不**寫成 `S03 enrolledIn C01`，也不刪掉任何一筆。查詢「確定修課」時只走 `enrolledIn`；要稽核時查 Claim 節點。

## 在 Neo4j 上執行

把 `out/load.cypher` 貼進 Neo4j Browser（或 `cypher-shell -f out/load.cypher`），在空白資料庫執行。
倒數第二段的驗證查詢應回傳 `courses=1, students=2`。
（本專案的 LPG 測試用 networkx 模擬；Cypher 腳本已產生但未在真實 Neo4j 上執行過。）

## 一分鐘離堂回答：Triple、LPG、Ontology、KG

- **Triple** 是 RDF 的最小陳述單位：主詞–述詞–受詞；受詞可以是 IRI，也可以是 literal（例如姓名），所以 triple ≠ 三個節點。
- **LPG** 是另一種圖資料模型：節點與邊都有 label 和 key-value 屬性，像 `semester` 可以直接掛在 `ENROLLED_IN` 邊上。
- **Ontology** 是語意模型：定義有哪些類別（Student、Course）、關係（enrolledIn）和規則（GraduateStudent ⊑ Student）。
- **KG** 把具語意的個體與關係整合起來；它可以用 RDF triples 或 LPG 儲存，並由 ontology 賦予意義。本專案同一份資料兩種模型的查詢結果一致，就是最好的說明。
