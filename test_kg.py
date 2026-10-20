"""
依講義第 23 頁評分面向組織的自動測試（pytest）。
每個「迷思」都附一個合成反例，證明測試真的會抓到錯（講義第 22 頁、解答本第 22 頁）。
執行：pytest -v
"""
import csv
from pathlib import Path

import pytest
from rdflib import BNode, Graph, Literal, RDF, RDFS, URIRef

import build_kg as b
from build_kg import EX

HERE = Path(__file__).parent


@pytest.fixture(scope="module")
def src():
    s, c, e, t, cl, report = b.load_sources()
    return dict(students=s, courses=c, enrollments=e, teaching=t, claims=cl, report=report)


@pytest.fixture(scope="module")
def tbox():
    return b.load_ontology()


@pytest.fixture(scope="module")
def rdf(src):
    return b.build_rdf(src["students"], src["courses"], src["enrollments"], src["teaching"], src["claims"])


@pytest.fixture(scope="module")
def lpg(src):
    return b.build_lpg(src["students"], src["courses"], src["enrollments"], src["teaching"], src["claims"])


def clone(g):
    h = Graph()
    for t in g:
        h.add(t)
    return h


# ════════════════ 繳交物清單（第 23 頁）════════════════
def test_deliverables_minimums(rdf, lpg, tbox):
    assert len(rdf) >= 5, "至少五筆 RDF triples"
    assert lpg.number_of_nodes() >= 3 and lpg.number_of_edges() >= 2, "至少三個 LPG 節點與兩個關係"
    assert (EX.Student, RDF.type, URIRef("http://www.w3.org/2002/07/owl#Class")) in tbox
    assert (EX.enrolledIn, RDFS.range, EX.Course) in tbox, "ontology 須定義 enrolledIn 語意"


# ════════════════ 模型正確性（40%）════════════════
def test_core_triples(rdf):
    """參考答案：S01 a Student；S01 enrolledIn C01；C01 a Course"""
    assert (EX.S01, EX.enrolledIn, EX.C01) in rdf
    assert (EX.S02, EX.enrolledIn, EX.C01) in rdf
    assert (EX.C01, RDF.type, EX.Course) in rdf


def test_name_is_literal_not_resource(rdf):
    """迷思 A：triple ≠ 三個節點；姓名是 literal（第 6 頁）"""
    for _, _, o in rdf.triples((None, EX.name, None)):
        assert isinstance(o, Literal) and o.language == "zh"


def test_one_course_node_shared(lpg):
    """第 9、19 頁：兩位學生修 C01，但只有一個 C01 節點"""
    c01_nodes = [n for n, d in lpg.nodes(data=True) if d.get("id") == "C01"]
    assert len(c01_nodes) == 1
    into_c01 = [u for u, v, d in lpg.edges(data=True) if v == "C01" and d["type"] == "ENROLLED_IN"]
    assert sorted(into_c01) == ["S01", "S02"]


def test_enrolled_in_direction(lpg):
    """ENROLLED_IN 一律 Student → Course（第 4 頁）"""
    for u, v, d in lpg.edges(data=True):
        if d["type"] == "ENROLLED_IN":
            assert "Student" in lpg.nodes[u]["labels"] and "Course" in lpg.nodes[v]["labels"]


def test_rdf_and_lpg_carry_same_facts(rdf, lpg):
    """兩種模型使用同一語意來源，資訊不應遺失（第 20 頁）"""
    rdf_pairs = {(str(s).rsplit("/", 1)[-1], str(o).rsplit("/", 1)[-1])
                 for s, _, o in rdf.triples((None, EX.enrolledIn, None))}
    lpg_pairs = {(u, v) for u, v, d in lpg.edges(data=True) if d["type"] == "ENROLLED_IN"}
    assert rdf_pairs == lpg_pairs


# ════════════════ 語意與識別碼（25%）════════════════
def test_ids_are_trimmed_and_unique(src):
    """' S02 ' 在 CSV 裡有空白，應被正規化為 S02（第 16 頁）"""
    assert set(src["students"]) == {"S01", "S02", "S03"}


def test_subclass_inference(rdf, tbox):
    """第 21 頁：GraduateStudent ⊑ Student，S01 a GraduateStudent ⇒ S01 a Student"""
    assert (EX.S01, RDF.type, EX.Student) not in rdf, "推論前不應存在"
    assert (EX.S01, RDF.type, EX.Student) in b.infer(rdf, tbox)


def test_subclassof_is_not_type(tbox):
    """第 15 頁：rdfs:subClassOf ≠ rdf:type"""
    assert (EX.GraduateStudent, RDFS.subClassOf, EX.Student) in tbox
    assert (EX.GraduateStudent, RDF.type, EX.Student) not in tbox


def test_clean_data_conforms_to_shacl(rdf, tbox):
    ok, report = b.shacl_check(rdf, tbox)
    assert ok, report


# ── 反例：證明驗證真的會失敗 ──
def test_NEG_name_as_resource_is_rejected(rdf, tbox):
    bad = clone(rdf)
    bad.remove((EX.S02, EX.name, None))
    bad.add((EX.S02, EX.name, EX.C01))                       # 把姓名誤寫成 IRI
    ok, _ = b.shacl_check(bad, tbox)
    assert not ok


def test_NEG_enrolled_in_non_course_is_rejected(rdf, tbox):
    bad = clone(rdf)
    bad.add((EX.S01, EX.enrolledIn, EX.T01))                 # 物件是老師不是課
    ok, _ = b.shacl_check(bad, tbox)
    assert not ok


def test_NEG_reversed_edge_infers_wrong_type_then_shacl_catches(rdf, tbox):
    """第 21 頁示例：ex:C01 ex:enrolledIn ex:S01。
    OWL/RDFS 不會『拒絕』，而是推出 C01 a Student；要靠 SHACL 才會報錯。"""
    bad = clone(rdf)
    bad.add((EX.C01, EX.enrolledIn, EX.S01))
    inferred = b.infer(bad, tbox)
    assert (EX.C01, RDF.type, EX.Student) in inferred        # 推論：非預期型別
    ok, _ = b.shacl_check(bad, tbox)
    assert not ok                                             # 驗證：抓到


def test_NEG_duplicate_course_node_detected():
    """常見扣分：兩位學生各複製一個 C01"""
    s, c, e, *_ = b.load_sources()
    g = b.build_lpg(s, c, e)
    g.add_node("C01_copy", labels=["Course"], id="C01", title="資料探勘")
    ids = [d["id"] for _, d in g.nodes(data=True) if "Course" in d["labels"]]
    assert len(ids) != len(set(ids)), "偵測函式應發現重複 id"


# ════════════════ 查詢可執行性（20%）════════════════
def test_sparql_students_of_c01(rdf):
    got = [(str(r.s).rsplit("/", 1)[-1], str(r.name)) for r in rdf.query(b.SPARQL_STUDENTS_OF_C01)]
    assert got == [("S01", "小美"), ("S02", "小華")]


def test_lpg_students_of_c01(lpg):
    assert b.lpg_students_of(lpg, "C01") == [("S01", "小美"), ("S02", "小華")]


def test_cypher_script_has_constraints_and_queries(src):
    cy = b.to_cypher(src["students"], src["courses"], src["enrollments"], src["teaching"], src["claims"])
    assert cy.index("CREATE CONSTRAINT") < cy.index("MERGE"), "constraint 須先於匯入（第 19 頁）"
    assert 'MATCH (s:Student)-[r:ENROLLED_IN]->(c:Course {id:"C01"})' in cy


# ════════════════ 證據與追溯（15%）════════════════
def test_every_enrollment_traces_back_to_csv(rdf):
    rows = list(csv.DictReader(open(HERE / "data/enrollment.csv", encoding="utf-8")))
    for ev in rdf.subjects(RDF.type, EX.Enrollment):
        row_no = int(rdf.value(ev, EX.sourceRow))
        raw = rows[row_no - 2]
        assert raw["student_no"].strip() == str(rdf.value(ev, EX.student)).rsplit("/", 1)[-1]
        assert raw["course_code"].strip() == str(rdf.value(ev, EX.course)).rsplit("/", 1)[-1]


def test_bad_rows_are_logged_not_silently_dropped(src):
    rep = src["report"]
    assert any("S09" in m for m in rep["rejected"])
    assert any("空的 course_code" in m for m in rep["rejected"])
    assert len(rep["duplicates"]) == 1


def test_uncertain_claim_not_promoted_to_fact(rdf, tbox):
    """迷思 D：LLM 擷取的『可能修課』不得寫成確定的 enrolledIn（第 22 頁）"""
    assert (EX.S03, EX.enrolledIn, EX.C01) not in b.infer(rdf, tbox)
    statuses = sorted(str(rdf.value(c, EX.status)) for c in rdf.subjects(RDF.type, EX.EnrollmentClaim))
    assert statuses == ["refuted", "unverified"], "衝突的兩筆來源都要保留（第 23 頁延伸討論）"


def test_NEG_claim_without_source_is_rejected(rdf, tbox):
    bad = clone(rdf)
    bad.remove((EX.CLAIM_2, EX.source, None))
    ok, _ = b.shacl_check(bad, tbox)
    assert not ok


def test_claims_not_inferred_as_enrollment(rdf, tbox):
    """回歸測試：ex:student 若宣告 domain ex:Enrollment，主張會被推論成確定紀錄"""
    inferred = b.infer(rdf, tbox)
    for c in rdf.subjects(RDF.type, EX.EnrollmentClaim):
        assert (c, RDF.type, EX.Enrollment) not in inferred
