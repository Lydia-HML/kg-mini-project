// 自動產生：python build_kg.py ── 可在 Neo4j Browser / cypher-shell 執行
CREATE CONSTRAINT student_id IF NOT EXISTS FOR (s:Student) REQUIRE s.id IS UNIQUE;
CREATE CONSTRAINT course_id  IF NOT EXISTS FOR (c:Course)  REQUIRE c.id IS UNIQUE;

MERGE (s:Student {id:"S01"}) SET s.name="Judy" SET s:GraduateStudent;
MERGE (s:Student {id:"S02"}) SET s.name="Albert";
MERGE (s:Student {id:"S03"}) SET s.name="Anita";
MERGE (c:Course {id:"C01"}) SET c.title="Data Mining and Knowledge Discovery", c.course_no="MI5110701";
MERGE (c:Course {id:"C02"}) SET c.title="Information Networks", c.course_no="MI4206301";

MATCH (s:Student {id:"S01"}), (c:Course {id:"C01"}) MERGE (s)-[r:ENROLLED_IN {semester:"115-1"}]->(c) SET r.recorded_on=date("2026-09-01"), r.source="enrollment.csv:2";
MATCH (s:Student {id:"S02"}), (c:Course {id:"C01"}) MERGE (s)-[r:ENROLLED_IN {semester:"115-1"}]->(c) SET r.recorded_on=date("2026-09-02"), r.source="enrollment.csv:3";
MATCH (s:Student {id:"S03"}), (c:Course {id:"C02"}) MERGE (s)-[r:ENROLLED_IN {semester:"115-1"}]->(c) SET r.recorded_on=date("2026-09-03"), r.source="enrollment.csv:5";
MERGE (t:Teacher {id:"T01"}) SET t.name="Lydia Lin" WITH t MATCH (c:Course {id:"C01"}) MERGE (t)-[:TEACHES {year:2026}]->(c);
MERGE (t:Teacher {id:"T01"}) SET t.name="Lydia Lin" WITH t MATCH (c:Course {id:"C02"}) MERGE (t)-[:TEACHES {year:2026}]->(c);
MERGE (x:EnrollmentClaim {id:"CLAIM_2"}) SET x.status="unverified", x.source="llm_extraction:meeting_notes_1015", x.semester="115-1", x.recorded_on=date("2026-10-15") WITH x MATCH (s:Student {id:"S03"}), (c:Course {id:"C01"}) MERGE (x)-[:ABOUT_STUDENT]->(s) MERGE (x)-[:ABOUT_COURSE]->(c);
MERGE (x:EnrollmentClaim {id:"CLAIM_3"}) SET x.status="refuted", x.source="registrar_export_1016", x.semester="115-1", x.recorded_on=date("2026-10-16") WITH x MATCH (s:Student {id:"S03"}), (c:Course {id:"C01"}) MERGE (x)-[:ABOUT_STUDENT]->(s) MERGE (x)-[:ABOUT_COURSE]->(c);

// 驗證（第 19 頁）：C01 應有 1 門課、2 位學生
MATCH (c:Course {id:"C01"}) OPTIONAL MATCH (s:Student)-[:ENROLLED_IN]->(c)
RETURN count(DISTINCT c) AS courses, count(DISTINCT s) AS students;

// 查詢（第 13 頁）：選 C01 的學生
MATCH (s:Student)-[r:ENROLLED_IN]->(c:Course {id:"C01"})
RETURN s.id, s.name, r.semester, r.source ORDER BY s.id;
