from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_agent_status_controls_are_declared_and_bound():
    resource_h = (ROOT / "resource.h").read_text(encoding="utf-8")
    rc = (ROOT / "OrobrosTest.rc").read_text(encoding="utf-8")
    header = (ROOT / "OrobrosTestDlg.h").read_text(encoding="utf-8")
    cpp = (ROOT / "OrobrosTestDlg.cpp").read_text(encoding="utf-8")

    assert "IDC_STATIC_AGENT_STATUS_LABEL" in resource_h
    assert "IDC_STATIC_AGENT_STATUS" in resource_h
    assert "IDC_STATIC_AGENT_STATUS_LABEL" in rc
    assert "IDC_STATIC_AGENT_STATUS" in rc
    assert "CStatic m_agentStatusLabel" in header
    assert "CStatic m_agentStatusText" in header
    assert "DDX_Control(pDX, IDC_STATIC_AGENT_STATUS_LABEL, m_agentStatusLabel)" in cpp
    assert "DDX_Control(pDX, IDC_STATIC_AGENT_STATUS, m_agentStatusText)" in cpp


def test_agent_status_is_updated_on_key_process_states():
    cpp = (ROOT / "OrobrosTestDlg.cpp").read_text(encoding="utf-8")

    assert "void COrobrosTestDlg::SetAgentStatus" in cpp
    for expected in [
        "대기 중",
        "로그 선택됨",
        "시작 중",
        "실행 중",
        "입력 대기",
        "최종확정 대기",
        "답변 전송 중",
        "중지 중",
        "완료",
        "오류",
    ]:
        assert expected in cpp

    assert cpp.count("SetAgentStatus(") >= 8


def test_load_log_repairs_invalid_command_before_focus_log_update():
    cpp = (ROOT / "OrobrosTestDlg.cpp").read_text(encoding="utf-8")
    header = (ROOT / "OrobrosTestDlg.h").read_text(encoding="utf-8")

    assert "static CString DefaultMaintenanceCommand()" in header
    assert "CString COrobrosTestDlg::DefaultMaintenanceCommand()" in cpp
    assert "run_maintenance_with_review.py" in cpp
    assert "python.exe" in cpp
    assert "command.Find(L\"run_maintenance_with_review.py\") < 0" in cpp
    assert "command = DefaultMaintenanceCommand();" in cpp
    assert "[WARN] command가 정비보고서 기본 실행기가 아니어서 기본 command로 복구했습니다." in cpp


def test_agent_status_messages_are_accumulated_in_transcript_without_duplicates():
    cpp = (ROOT / "OrobrosTestDlg.cpp").read_text(encoding="utf-8")
    header = (ROOT / "OrobrosTestDlg.h").read_text(encoding="utf-8")

    assert "CString m_lastAgentStatusText" in header
    assert "[AGENT STATUS]" in cpp
    assert "if (text != m_lastAgentStatusText)" in cpp
    assert "m_lastAgentStatusText = text;" in cpp
    assert "AppendText(L\"[AGENT STATUS] \" + text + L\"\\r\\n\");" in cpp


def test_agent_progress_listview_displays_status_history():
    resource_h = (ROOT / "resource.h").read_text(encoding="utf-8")
    rc = (ROOT / "OrobrosTest.rc").read_text(encoding="utf-8")
    header = (ROOT / "OrobrosTestDlg.h").read_text(encoding="utf-8")
    cpp = (ROOT / "OrobrosTestDlg.cpp").read_text(encoding="utf-8")
    app_cpp = (ROOT / "OrobrosTest.cpp").read_text(encoding="utf-8")

    assert "IDC_LIST_AGENT_PROGRESS" in resource_h
    assert "SysListView32" in rc
    assert "IDC_LIST_AGENT_PROGRESS" in rc
    assert "CListCtrl m_agentProgressList" in header
    assert "int m_agentProgressSeq" in header
    assert "CString m_currentAgentName" in header
    assert "InitializeAgentProgressList" in header
    assert "AddAgentProgress" in header
    assert "DDX_Control(pDX, IDC_LIST_AGENT_PROGRESS, m_agentProgressList)" in cpp
    assert "InsertColumn(0, L\"No\"" in cpp
    assert "InsertColumn(1, L\"Agent\"" in cpp
    assert "InsertColumn(2, L\"State\"" in cpp
    assert "InsertColumn(3, L\"Detail\"" in cpp
    for agent_name in [
        "Context & Field Interview Agent",
        "Persistent Memory Retrieval Agent",
        "Diagnostic Reasoning Agent",
        "Procedure & Priority Agent",
        "Trust Gate Agent",
        "Feedback Learning Agent",
    ]:
        assert agent_name in cpp or agent_name in (ROOT / "tools" / "run_maintenance_with_review.py").read_text(encoding="utf-8")
    assert "[AGENT]" in (ROOT / "tools" / "run_maintenance_with_review.py").read_text(encoding="utf-8")
    assert "UpdateCurrentAgentFromOutput" in cpp
    assert "AddAgentProgress(state, detail);" in cpp
    assert "m_agentProgressList.DeleteAllItems();" in cpp
    assert "ICC_LISTVIEW_CLASSES" in app_cpp
