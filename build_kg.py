"""
KG Mini Project：同一份 CSV → (1) RDF 知識圖譜  (2) Labeled Property Graph
對應講義第 16（Mapping）、19（Cypher）、20（Turtle）、21（推論/驗證）、23（Mini Project）頁。

執行：python build_kg.py
產出：out/kg.ttl、out/load.cypher、out/mapping_report.json
"""
import csv
import json
from pathlib import Path

import networkx as nx
import owlrl
from pyshacl import validate
from rdflib import Graph, Literal, Namespace, RDF, RDFS, XSD

HERE = Path(__file__).parent
DATA, OUT = HERE / "data", HERE / "out"
EX = Namespace("https://ex.org/")


# ───────────────────────── 1. 讀取與清理（第 16 頁）─────────────────────────
def read_csv(name):
    with open(DATA / name, encoding="utf-8") as f:
        # 從第 2 列開始編號，讓 sourceRow 對得上試算表的列號
        return [(i, {k.strip(): (v or "").strip() for k, v in row.items()})
                for i, row in enumerate(csv.DictReader(f), start=2)]


def load_sources():
    report = {"rejected": [], "duplicates": [], "warnings": []}

    students = {}
    for row_no, r in read_csv("students.csv"):
        sid = r["student_no"]                       # trim 已在 read_csv 完成
        if sid in students:
            report["warnings"].append(f"students.csv:{row_no} 重複學號 {sid}")
            continue
        students[sid] = {**r, "_row": row_no}

    courses = {}
    for row_no, r in read_csv("courses.csv"):
        courses[r["course_code"]] = {**r, "_row": row_no}

    enrollments, seen = [], {}
    for row_no, r in read_csv("enrollment.csv"):
        sid, cid, sem = r["student_no"], r["course_code"], r["semester"]
        where = f"enrollment.csv:{row_no}"
        if not cid:
            report["rejected"].append(f"{where} 空的 course_code")
            continue
        if sid not in students:
            report["rejected"].append(f"{where} 無法對應的學號 {sid}")
            continue
        if cid not in courses:
            report["rejected"].append(f"{where} 無法對應的課號 {cid}")
            continue
        key = (sid, cid, sem)
        if key in seen:                              # 同學期同課＝重複紀錄，不是重修
            report["duplicates"].append(f"{where} 與第 {seen[key]} 列重複 {key}")
            continue
        seen[key] = row_no
        enrollments.append({**r, "_row": row_no})

    teaching = [{**r, "_row": n} for n, r in read_csv("teaching.csv")]

    # 未確認／衝突的主張：只存成 EnrollmentClaim，絕不升級為確定的 ENROLLED_IN
    claims = []
    for row_no, r in read_csv("claims.csv"):
        if r["student_no"] in students and r["course_code"] in courses:
            claims.append({**r, "_row": row_no})
        else:
            report["rejected"].append(f"claims.csv:{row_no} 無法對應的 ID")

    report["counts"] = {"students": len(students), "courses": len(courses),
                        "teachers": len({r["teacher_no"] for r in teaching}), "teaching_links": len(teaching), "enrollments": len(enrollments),
                        "claims": len(claims)}
    return students, courses, enrollments, teaching, claims, report


# ───────────────────────── 2. RDF（ABox，個體層）─────────────────────────
def build_rdf(students, courses, enrollments, teaching=(), claims=()):
    g = Graph()
    g.bind("ex", EX)
    for sid, s in students.items():
        node = EX[sid]
        g.add((node, RDF.type, EX.GraduateStudent if s["level"] == "graduate" else EX.Student))
        g.add((node, EX.name, Literal(s["name"], lang="en")))        # literal，不是第三個實體
    for cid, c in courses.items():
        node = EX[cid]
        g.add((node, RDF.type, EX.Course))
        g.add((node, RDFS.label, Literal(c["title"], lang="en")))
    for e in enrollments:
        s, c = EX[e["student_no"]], EX[e["course_code"]]
        g.add((s, EX.enrolledIn, c))                                   # 簡潔的直接邊（第 20 頁）
        ev = EX[f"ENR_{e['student_no']}_{e['course_code']}_{e['semester']}"]
        g.add((ev, RDF.type, EX.Enrollment))                           # 事件節點保留脈絡（第 12 頁）
        g.add((ev, EX.student, s))
        g.add((ev, EX.course, c))
        g.add((ev, EX.semester, Literal(e["semester"], datatype=XSD.string)))
        g.add((ev, EX.recordedOn, Literal(e["recorded_on"], datatype=XSD.date)))
        g.add((ev, EX.sourceFile, Literal("enrollment.csv")))
        g.add((ev, EX.sourceRow, Literal(e["_row"], datatype=XSD.integer)))
    for t in teaching:
        node = EX[t["teacher_no"]]
        g.add((node, RDF.type, EX.Teacher))
        g.add((node, RDFS.label, Literal(t["name"], lang="en")))
        g.add((node, EX.teaches, EX[t["course_code"]]))
    for c in claims:
        cl = EX[f"CLAIM_{c['_row']}"]
        g.add((cl, RDF.type, EX.EnrollmentClaim))
        g.add((cl, EX.student, EX[c["student_no"]]))
        g.add((cl, EX.course, EX[c["course_code"]]))
        g.add((cl, EX.semester, Literal(c["semester"], datatype=XSD.string)))
        g.add((cl, EX.status, Literal(c["status"])))
        g.add((cl, EX.source, Literal(c["source"])))
        g.add((cl, EX.recordedOn, Literal(c["recorded_on"], datatype=XSD.date)))
    return g


def load_ontology():
    return Graph().parse(HERE / "ontology.ttl")


def infer(abox, tbox):
    """RDFS 推論：GraduateStudent ⊑ Student ⇒ ex:S01 a ex:Student"""
    g = Graph()
    for t in abox: g.add(t)
    for t in tbox: g.add(t)
    owlrl.DeductiveClosure(owlrl.RDFS_Semantics).expand(g)
    return g


def shacl_check(data_graph, tbox):
    shapes = Graph().parse(HERE / "shapes.ttl")
    # inference="none" 是刻意的：若先做 RDFS 推論，rdfs:range ex:Course 會把錯誤物件
    # （例如老師 T01）推成 Course，SHACL 的 sh:class 檢查就被「推論洗白」而通過。
    # ont_graph 仍提供 subClassOf，讓 targetClass ex:Student 涵蓋 GraduateStudent。
    conforms, _, text = validate(data_graph, shacl_graph=shapes, ont_graph=tbox,
                                 inference="none", abort_on_first=False)
    return conforms, text


SPARQL_STUDENTS_OF_C01 = """
PREFIX ex: <https://ex.org/>
SELECT ?s ?name WHERE {
  ?s ex:enrolledIn ex:C01 ;
     ex:name ?name .
} ORDER BY ?s
"""

SPARQL_WITH_PROVENANCE = """
PREFIX ex: <https://ex.org/>
SELECT ?s ?semester ?recordedOn ?file ?row WHERE {
  ?e a ex:Enrollment ; ex:student ?s ; ex:course ex:C01 ;
     ex:semester ?semester ; ex:recordedOn ?recordedOn ;
     ex:sourceFile ?file ; ex:sourceRow ?row .
} ORDER BY ?s
"""


# ───────────────────────── 3. Labeled Property Graph ─────────────────────────
def build_lpg(students, courses, enrollments, teaching=(), claims=()):
    """以 networkx MultiDiGraph 模擬 LPG：節點有 label 與屬性，邊有型別與屬性。"""
    g = nx.MultiDiGraph()
    for t in teaching:
        g.add_node(t["teacher_no"], labels=["Teacher"], id=t["teacher_no"], name=t["name"])
    for c in claims:   # 主張是「邊上的屬性」不夠用的情況 → 建成節點
        cid = f"CLAIM_{c['_row']}"
        g.add_node(cid, labels=["EnrollmentClaim"], id=cid, status=c["status"],
                   source=c["source"], semester=c["semester"])
    for sid, s in students.items():
        labels = ["Student"] + (["GraduateStudent"] if s["level"] == "graduate" else [])
        g.add_node(sid, labels=labels, id=sid, name=s["name"])
    for cid, c in courses.items():
        g.add_node(cid, labels=["Course"], id=cid, title=c["title"])
    for e in enrollments:
        g.add_edge(e["student_no"], e["course_code"], type="ENROLLED_IN",
                   semester=e["semester"], recorded_on=e["recorded_on"],
                   source=f"enrollment.csv:{e['_row']}")
    for t in teaching:
        g.add_edge(t["teacher_no"], t["course_code"], type="TEACHES", year=t["year"])
    for c in claims:
        cid = f"CLAIM_{c['_row']}"
        g.add_edge(cid, c["student_no"], type="ABOUT_STUDENT")
        g.add_edge(cid, c["course_code"], type="ABOUT_COURSE")
    return g


def lpg_students_of(g, course_id):
    """等價於 MATCH (s:Student)-[:ENROLLED_IN]->(c:Course {id:$id}) RETURN s.id, s.name"""
    return sorted(
        (g.nodes[u]["id"], g.nodes[u]["name"])
        for u, v, d in g.edges(data=True)
        if d["type"] == "ENROLLED_IN" and v == course_id
        and "Student" in g.nodes[u]["labels"] and "Course" in g.nodes[v]["labels"]
    )


def to_cypher(students, courses, enrollments, teaching=(), claims=()):
    q = lambda x: '"' + str(x).replace("\\", "\\\\").replace('"', '\\"') + '"'
    lines = [
        "// 自動產生：python build_kg.py ── 可在 Neo4j Browser / cypher-shell 執行",
        "CREATE CONSTRAINT student_id IF NOT EXISTS FOR (s:Student) REQUIRE s.id IS UNIQUE;",
        "CREATE CONSTRAINT course_id  IF NOT EXISTS FOR (c:Course)  REQUIRE c.id IS UNIQUE;",
        "",
    ]
    for sid, s in students.items():
        extra = " SET s:GraduateStudent" if s["level"] == "graduate" else ""
        lines.append(f"MERGE (s:Student {{id:{q(sid)}}}) SET s.name={q(s['name'])}{extra};")
    for cid, c in courses.items():
        lines.append(f"MERGE (c:Course {{id:{q(cid)}}}) SET c.title={q(c['title'])};")
    lines.append("")
    for e in enrollments:
        lines.append(
            f"MATCH (s:Student {{id:{q(e['student_no'])}}}), (c:Course {{id:{q(e['course_code'])}}}) "
            f"MERGE (s)-[r:ENROLLED_IN {{semester:{q(e['semester'])}}}]->(c) "
            f"SET r.recorded_on=date({q(e['recorded_on'])}), r.source={q('enrollment.csv:' + str(e['_row']))};"
        )
    for t in teaching:
        lines.append(
            f"MERGE (t:Teacher {{id:{q(t['teacher_no'])}}}) SET t.name={q(t['name'])} "
            f"WITH t MATCH (c:Course {{id:{q(t['course_code'])}}}) "
            f"MERGE (t)-[:TEACHES {{year:{t['year']}}}]->(c);")
    for c in claims:
        cid = f"CLAIM_{c['_row']}"
        lines.append(
            f"MERGE (x:EnrollmentClaim {{id:{q(cid)}}}) SET x.status={q(c['status'])}, "
            f"x.source={q(c['source'])}, x.semester={q(c['semester'])}, x.recorded_on=date({q(c['recorded_on'])}) "
            f"WITH x MATCH (s:Student {{id:{q(c['student_no'])}}}), (c:Course {{id:{q(c['course_code'])}}}) "
            f"MERGE (x)-[:ABOUT_STUDENT]->(s) MERGE (x)-[:ABOUT_COURSE]->(c);")
    lines += [
        "",
        "// 驗證（第 19 頁）：C01 應有 1 門課、2 位學生",
        'MATCH (c:Course {id:"C01"}) OPTIONAL MATCH (s:Student)-[:ENROLLED_IN]->(c)',
        "RETURN count(DISTINCT c) AS courses, count(DISTINCT s) AS students;",
        "",
        "// 查詢（第 13 頁）：選 C01 的學生",
        'MATCH (s:Student)-[r:ENROLLED_IN]->(c:Course {id:"C01"})',
        "RETURN s.id, s.name, r.semester, r.source ORDER BY s.id;",
    ]
    return "\n".join(lines) + "\n"


# ───────────────────────── main ─────────────────────────
def main():
    OUT.mkdir(exist_ok=True)
    students, courses, enrollments, teaching, claims, report = load_sources()
    src = (students, courses, enrollments, teaching, claims)

    tbox = load_ontology()
    abox = build_rdf(*src)
    abox.serialize(OUT / "kg.ttl", format="turtle")
    (OUT / "load.cypher").write_text(to_cypher(*src), encoding="utf-8")

    conforms, shacl_text = shacl_check(abox, tbox)
    report["shacl_conforms"] = conforms
    report["triples"] = len(abox)
    (OUT / "mapping_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2),
                                             encoding="utf-8")

    kg = infer(abox, tbox)
    lpg = build_lpg(*src)

    print("== Mapping 報告 ==")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print("\n== SPARQL：選 C01 的學生 ==")
    for row in abox.query(SPARQL_STUDENTS_OF_C01):
        print(f"  {row.s.split('/')[-1]}  {row.name}")
    print("\n== SPARQL：附來源 ==")
    for row in abox.query(SPARQL_WITH_PROVENANCE):
        print(f"  {row.s.split('/')[-1]}  {row.semester}  {row.recordedOn}  {row.file}:{row.row}")
    print("\n== LPG（Cypher 等價查詢）：選 C01 的學生 ==")
    for sid, name in lpg_students_of(lpg, "C01"):
        print(f"  {sid}  {name}")
    print(f"\n== 推論：ex:S01 a ex:Student ? {(EX.S01, RDF.type, EX.Student) in kg}"
          f"（推論前 {(EX.S01, RDF.type, EX.Student) in abox}）")
    print(f"== SHACL 驗證通過：{conforms}")


if __name__ == "__main__":
    main()
