#include "framework.h"
#include "OrobrosTest.h"
#include "OrobrosTestDlg.h"
#include <afxdlgs.h>
#include <vector>
#include <algorithm>
#include <fstream>
#include <cwctype>

#ifdef _DEBUG
#define new DEBUG_NEW
#endif

BEGIN_MESSAGE_MAP(COrobrosTestDlg, CDialogEx)
    ON_BN_CLICKED(IDC_BUTTON_START, &COrobrosTestDlg::OnBnClickedStart)
    ON_BN_CLICKED(IDC_BUTTON_SEND, &COrobrosTestDlg::OnBnClickedSend)
    ON_BN_CLICKED(IDC_BUTTON_STOP, &COrobrosTestDlg::OnBnClickedStop)
    ON_BN_CLICKED(IDC_BUTTON_LOAD_LOG, &COrobrosTestDlg::OnBnClickedLoadLog)
    ON_MESSAGE(WM_PIPE_OUTPUT, &COrobrosTestDlg::OnPipeOutput)
    ON_MESSAGE(WM_PROCESS_EXITED, &COrobrosTestDlg::OnProcessExited)
END_MESSAGE_MAP()

COrobrosTestDlg::COrobrosTestDlg(CWnd* pParent) : CDialogEx(IDD_OROBROSTEST_DIALOG, pParent) {}


CString COrobrosTestDlg::DefaultAgentName()
{
    return L"Diagnostic Reasoning Agent";
}

CString COrobrosTestDlg::DefaultMaintenanceCommand()
{
    return L"\"C:\\Users\\yjs\\AppData\\Local\\hermes\\hermes-agent\\venv\\Scripts\\python.exe\" \"C:\\Users\\yjs\\Desktop\\JAN\\OrobrosTest\\tools\\run_maintenance_with_review.py\" --python \"C:\\Users\\yjs\\AppData\\Local\\hermes\\hermes-agent\\venv\\Scripts\\python.exe\" --project-root \"C:\\Users\\yjs\\Desktop\\JAN\\OrobrosTest\" --log-root \"C:\\Users\\yjs\\Desktop\\JAN\\LOG\" --out-doc \"C:\\Users\\yjs\\Desktop\\JAN\\OrobrosTest\\out\\JAN_maintenance_report_ui.docx\" --out-json \"C:\\Users\\yjs\\Desktop\\JAN\\OrobrosTest\\out\\JAN_maintenance_report_ui.json\" --review-history-dir \"C:\\Users\\yjs\\Desktop\\JAN\\OrobrosTest\\out\" --review-out-dir \"C:\\Users\\yjs\\Desktop\\JAN\\OrobrosTest\\out\\ouroboros_review_ui\"";
}

void COrobrosTestDlg::DoDataExchange(CDataExchange* pDX)
{
    CDialogEx::DoDataExchange(pDX);
    DDX_Control(pDX, IDC_EDIT_COMMAND, m_commandEdit);
    DDX_Control(pDX, IDC_EDIT_CONTEXT, m_contextEdit);
    DDX_Control(pDX, IDC_EDIT_TRANSCRIPT, m_transcriptEdit);
    DDX_Control(pDX, IDC_EDIT_ANSWER, m_answerEdit);
    DDX_Control(pDX, IDC_BUTTON_START, m_startButton);
    DDX_Control(pDX, IDC_BUTTON_SEND, m_sendButton);
    DDX_Control(pDX, IDC_BUTTON_STOP, m_stopButton);
    DDX_Control(pDX, IDC_STATIC_AGENT_STATUS_LABEL, m_agentStatusLabel);
    DDX_Control(pDX, IDC_STATIC_AGENT_STATUS, m_agentStatusText);
    DDX_Control(pDX, IDC_LIST_AGENT_PROGRESS, m_agentProgressList);
}

BOOL COrobrosTestDlg::OnInitDialog()
{
    CDialogEx::OnInitDialog();
    SetWindowText(L"OrobrosTest - Maintenance Report Runner");
    m_commandEdit.SetWindowText(DefaultMaintenanceCommand());
    m_currentAgentName = DefaultAgentName();
    m_contextEdit.SetWindowText(L"우선점검: 시스템제어기조립체; 해결: (해결 시 조치항목 입력)");
    SetDlgItemTextW(IDC_BUTTON_LOAD_LOG, L"로그 읽기");
    m_sendButton.EnableWindow(FALSE);
    m_stopButton.EnableWindow(FALSE);
    InitializeAgentProgressList();
    SetAgentStatus(L"대기 중", L"명령을 입력하고 Start를 누르세요.");
    AppendText(L"[Ready] Start를 누르면 전체 시험 로그를 읽어 이상탐지/원인분류/장기위험 예측 후 정비 Word 보고서를 생성합니다.\r\n");
    return TRUE;
}

CString COrobrosTestDlg::QuoteArg(const CString& s)
{
    CString out = L"\"";
    for (int i = 0; i < s.GetLength(); ++i) {
        if (s[i] == L'\"') out += L"\\\"";
        else out += s[i];
    }
    out += L"\"";
    return out;
}

CString COrobrosTestDlg::FormatWin32Error(DWORD error)
{
    LPWSTR buffer = nullptr;
    DWORD chars = FormatMessageW(
        FORMAT_MESSAGE_ALLOCATE_BUFFER | FORMAT_MESSAGE_FROM_SYSTEM | FORMAT_MESSAGE_IGNORE_INSERTS,
        nullptr,
        error,
        MAKELANGID(LANG_NEUTRAL, SUBLANG_DEFAULT),
        reinterpret_cast<LPWSTR>(&buffer),
        0,
        nullptr);

    CString message;
    if (chars && buffer) {
        message.Format(L"GetLastError=%lu (%s)", error, buffer);
        LocalFree(buffer);
    }
    else {
        message.Format(L"GetLastError=%lu", error);
    }
    message.Trim();
    return message;
}

CString COrobrosTestDlg::BuildCommandLine() const
{
    CString cmd, ctx;
    const_cast<CEdit&>(m_commandEdit).GetWindowText(cmd);
    const_cast<CEdit&>(m_contextEdit).GetWindowText(ctx);
    cmd.Trim();
    ctx.Trim();
    if (!ctx.IsEmpty()) {
        cmd += L" --operator-feedback ";
        cmd += QuoteArg(ctx);
    }
    return cmd;
}

CString COrobrosTestDlg::UpdateFocusLogArg(const CString& command, const CString& logPath)
{
    CString cmd = command;
    CString key = L"--focus-log";

    int pos = cmd.Find(key);
    while (pos >= 0) {
        int end = pos + key.GetLength();
        while (end < cmd.GetLength() && iswspace(cmd[end])) ++end;
        if (end < cmd.GetLength() && cmd[end] == L'\"') {
            ++end;
            while (end < cmd.GetLength() && cmd[end] != L'\"') ++end;
            if (end < cmd.GetLength()) ++end;
        }
        else {
            while (end < cmd.GetLength() && !iswspace(cmd[end])) ++end;
        }
        cmd.Delete(pos, end - pos);
        cmd.Trim();
        pos = cmd.Find(key);
    }

    if (!logPath.IsEmpty()) {
        cmd += L" --focus-log ";
        cmd += QuoteArg(logPath);
    }
    return cmd;
}

CString COrobrosTestDlg::LoadLogPreview(const CString& logPath, size_t maxBytes)
{
    std::ifstream in(CT2A(logPath, CP_UTF8), std::ios::binary);
    if (!in.is_open()) {
        return L"";
    }

    std::string raw;
    raw.resize(maxBytes);
    in.read(raw.data(), static_cast<std::streamsize>(maxBytes));
    raw.resize(static_cast<size_t>(in.gcount()));

    CString preview;
    if (!raw.empty()) {
        preview = Utf8ToWide(raw.data(), static_cast<int>(raw.size()));
        preview.Replace(L"\r", L"");
    }
    return preview;
}

void COrobrosTestDlg::AppendText(const CString& text)
{
    int len = m_transcriptEdit.GetWindowTextLength();
    m_transcriptEdit.SetSel(len, len);
    m_transcriptEdit.ReplaceSel(text);
}

void COrobrosTestDlg::InitializeAgentProgressList()
{
    m_agentProgressList.SetExtendedStyle(LVS_EX_FULLROWSELECT | LVS_EX_GRIDLINES | LVS_EX_DOUBLEBUFFER);
    m_agentProgressList.InsertColumn(0, L"No", LVCFMT_LEFT, 38);
    m_agentProgressList.InsertColumn(1, L"Agent", LVCFMT_LEFT, 190);
    m_agentProgressList.InsertColumn(2, L"State", LVCFMT_LEFT, 95);
    m_agentProgressList.InsertColumn(3, L"Detail", LVCFMT_LEFT, 397);
}

void COrobrosTestDlg::AddAgentProgress(const CString& state, const CString& detail)
{
    if (!::IsWindow(m_agentProgressList.GetSafeHwnd())) {
        return;
    }

    CString seq;
    seq.Format(L"%d", ++m_agentProgressSeq);
    int row = m_agentProgressList.InsertItem(m_agentProgressList.GetItemCount(), seq);
    m_agentProgressList.SetItemText(row, 1, m_currentAgentName.IsEmpty() ? DefaultAgentName() : m_currentAgentName);
    m_agentProgressList.SetItemText(row, 2, state);
    m_agentProgressList.SetItemText(row, 3, detail);
    m_agentProgressList.EnsureVisible(row, FALSE);
}

void COrobrosTestDlg::UpdateCurrentAgentFromOutput(const CString& chunk)
{
    int agentMarker = chunk.Find(L"[AGENT]");
    if (agentMarker >= 0) {
        int nameStart = agentMarker + static_cast<int>(wcslen(L"[AGENT]"));
        int nameEnd = chunk.Find(L"|", nameStart);
        if (nameEnd < 0) {
            nameEnd = chunk.Find(L"\n", nameStart);
        }
        CString parsed = (nameEnd >= 0) ? chunk.Mid(nameStart, nameEnd - nameStart) : chunk.Mid(nameStart);
        parsed.Trim();
        if (!parsed.IsEmpty()) {
            m_currentAgentName = parsed;
            return;
        }
    }

    if (chunk.Find(L"[INTERVIEW_Q") >= 0) {
        m_currentAgentName = L"Context & Field Interview Agent";
    }
    else if (chunk.Find(L"[FINAL_CONFIRM_Q]") >= 0 || chunk.Find(L"[FINAL_CONFIRM_A]") >= 0) {
        m_currentAgentName = L"Trust Gate Agent";
    }
    else if (chunk.Find(L"[FINAL_CONFIRM]") >= 0 || chunk.Find(L"[DONE]") >= 0) {
        m_currentAgentName = L"Feedback Learning Agent";
    }
    else if (chunk.Find(L"[REVIEW]") >= 0) {
        m_currentAgentName = L"Trust Gate Agent";
    }
    else if (chunk.Find(L"ouroboros_review_loop.py") >= 0) {
        m_currentAgentName = L"Procedure & Priority Agent";
    }
    else if (chunk.Find(L"generate_maintenance_report.py") >= 0 || chunk.Find(L"[RUN]") >= 0) {
        m_currentAgentName = L"Diagnostic Reasoning Agent";
    }
}

void COrobrosTestDlg::SetAgentStatus(const CString& state, const CString& detail)
{
    CString text;
    if (detail.IsEmpty()) {
        text = state;
    }
    else {
        text.Format(L"%s - %s", state.GetString(), detail.GetString());
    }
    m_agentStatusText.SetWindowText(text);
    if (text != m_lastAgentStatusText) {
        m_lastAgentStatusText = text;
        AppendText(L"[AGENT STATUS] " + text + L"\r\n");
        AddAgentProgress(state, detail);
    }
}

CString COrobrosTestDlg::Utf8ToWide(const char* data, int len)
{
    if (len <= 0) return L"";
    int needed = MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, data, len, nullptr, 0);
    UINT cp = CP_UTF8;
    DWORD flags = MB_ERR_INVALID_CHARS;
    if (needed <= 0) {
        cp = CP_ACP;
        flags = 0;
        needed = MultiByteToWideChar(cp, flags, data, len, nullptr, 0);
    }
    CString out;
    wchar_t* buf = out.GetBuffer(needed + 1);
    int written = MultiByteToWideChar(cp, flags, data, len, buf, needed);
    buf[written] = 0;
    out.ReleaseBuffer(written);
    return out;
}

bool COrobrosTestDlg::StartProcess(const CString& commandLine)
{
    // Ouroboros is a Python/Rich-based CLI.  When it is launched from a
    // Windows GUI process, Python may default stderr/stdout to the system ANSI
    // code page (CP949 on this machine). Rich prints Unicode spinner glyphs
    // such as U+280B while generating the Codex interview question, and CP949
    // cannot encode them. Force the child Python process to use UTF-8 so the
    // stdout/stderr pipes receive valid UTF-8 instead of crashing before the
    // first question is displayed.
    SetEnvironmentVariableW(L"PYTHONUTF8", L"1");
    SetEnvironmentVariableW(L"PYTHONIOENCODING", L"utf-8");
    SetEnvironmentVariableW(L"NO_COLOR", L"1");
    SetEnvironmentVariableW(L"TERM", L"dumb");

    SECURITY_ATTRIBUTES sa{};
    sa.nLength = sizeof(SECURITY_ATTRIBUTES);
    sa.bInheritHandle = TRUE;

    if (!CreatePipe(&m_childStdOutRd, &m_childStdOutWr, &sa, 0)) {
        DWORD err = GetLastError();
        SetAgentStatus(L"오류", L"stdout pipe 생성 실패");
        AppendText(L"[ERROR] stdout pipe 생성 실패: " + FormatWin32Error(err) + L"\r\n");
        CloseProcessHandles();
        SetLastError(err);
        return false;
    }
    if (!SetHandleInformation(m_childStdOutRd, HANDLE_FLAG_INHERIT, 0)) {
        DWORD err = GetLastError();
        SetAgentStatus(L"오류", L"stdout pipe inherit 설정 실패");
        AppendText(L"[ERROR] stdout pipe inherit 설정 실패: " + FormatWin32Error(err) + L"\r\n");
        CloseProcessHandles();
        SetLastError(err);
        return false;
    }
    if (!CreatePipe(&m_childStdInRd, &m_childStdInWr, &sa, 0)) {
        DWORD err = GetLastError();
        SetAgentStatus(L"오류", L"stdin pipe 생성 실패");
        AppendText(L"[ERROR] stdin pipe 생성 실패: " + FormatWin32Error(err) + L"\r\n");
        CloseProcessHandles();
        SetLastError(err);
        return false;
    }
    if (!SetHandleInformation(m_childStdInWr, HANDLE_FLAG_INHERIT, 0)) {
        DWORD err = GetLastError();
        SetAgentStatus(L"오류", L"stdin pipe inherit 설정 실패");
        AppendText(L"[ERROR] stdin pipe inherit 설정 실패: " + FormatWin32Error(err) + L"\r\n");
        CloseProcessHandles();
        SetLastError(err);
        return false;
    }

    STARTUPINFO si{};
    si.cb = sizeof(si);
    si.hStdError = m_childStdOutWr;
    si.hStdOutput = m_childStdOutWr;
    si.hStdInput = m_childStdInRd;
    si.dwFlags |= STARTF_USESTDHANDLES;

    CString mutableCmd = commandLine;
    BOOL ok = CreateProcessW(
        nullptr,
        mutableCmd.GetBuffer(),
        nullptr,
        nullptr,
        TRUE,
        CREATE_NO_WINDOW,
        nullptr,
        nullptr,
        &si,
        &m_pi);
    mutableCmd.ReleaseBuffer();

    CloseHandle(m_childStdOutWr); m_childStdOutWr = nullptr;
    CloseHandle(m_childStdInRd);  m_childStdInRd = nullptr;

    if (!ok) {
        DWORD err = GetLastError();
        SetAgentStatus(L"오류", L"프로세스 실행 실패");
        CloseProcessHandles();
        SetLastError(err);
        return false;
    }

    m_running = true;
    SetAgentStatus(L"실행 중", L"agent가 요청을 처리하고 있습니다.");
    m_readerThread = std::thread(&COrobrosTestDlg::ReaderLoop, this);
    return true;
}

void COrobrosTestDlg::ReaderLoop()
{
    char buffer[4096];
    DWORD read = 0;
    while (m_running && m_childStdOutRd) {
        BOOL ok = ReadFile(m_childStdOutRd, buffer, sizeof(buffer), &read, nullptr);
        if (!ok || read == 0) break;
        CString chunk = Utf8ToWide(buffer, static_cast<int>(read));
        PostMessage(WM_PIPE_OUTPUT, 0, reinterpret_cast<LPARAM>(new CString(chunk)));
    }
    PostMessage(WM_PROCESS_EXITED, 0, 0);
}

bool COrobrosTestDlg::WriteAnswer(const CString& answer, DWORD* lastError)
{
    if (lastError) *lastError = ERROR_SUCCESS;

    if (!m_running || !m_childStdInWr) {
        if (lastError) *lastError = ERROR_INVALID_HANDLE;
        return false;
    }

    if (m_pi.hProcess && WaitForSingleObject(m_pi.hProcess, 0) != WAIT_TIMEOUT) {
        if (lastError) *lastError = ERROR_BROKEN_PIPE;
        return false;
    }

    CString line = answer + L"\r\n";
    int bytesNeeded = WideCharToMultiByte(CP_UTF8, 0, line, line.GetLength(), nullptr, 0, nullptr, nullptr);
    if (bytesNeeded <= 0) {
        if (lastError) *lastError = GetLastError();
        return false;
    }

    std::vector<char> bytes(static_cast<size_t>(bytesNeeded));
    if (WideCharToMultiByte(CP_UTF8, 0, line, line.GetLength(), bytes.data(), bytesNeeded, nullptr, nullptr) <= 0) {
        if (lastError) *lastError = GetLastError();
        return false;
    }

    DWORD written = 0;
    if (!WriteFile(m_childStdInWr, bytes.data(), static_cast<DWORD>(bytes.size()), &written, nullptr)) {
        if (lastError) *lastError = GetLastError();
        return false;
    }

    if (written != bytes.size()) {
        if (lastError) *lastError = ERROR_WRITE_FAULT;
        return false;
    }

    return true;
}

void COrobrosTestDlg::MaybeShowQuestionDialog(const CString& chunk)
{
    // child가 이미 종료됐거나 stdin handle이 닫힌 상태에서는 질문 Dialog를 띄우지 않는다.
    if (!m_running || !m_childStdInWr) {
        return;
    }

    CString currentCommand;
    m_commandEdit.GetWindowText(currentCommand);
    currentCommand.MakeLower();
    if (currentCommand.Find(L"ouroboros") < 0 && currentCommand.Find(L"run_maintenance_with_review.py") < 0) {
        return;
    }

    CString trimmed = chunk;
    trimmed.Trim();
    if (trimmed.IsEmpty()) return;

    // 한 번의 chunk에 여러 [INTERVIEW_Qn]이 같이 들어올 수 있으므로 모든 번호를 순회 처리한다.
    int scanPos = 0;
    while (true) {
        int marker = trimmed.Find(L"[INTERVIEW_Q", scanPos);
        if (marker < 0) break;

        int qNumPos = marker + static_cast<int>(wcslen(L"[INTERVIEW_Q"));
        if (qNumPos >= trimmed.GetLength()) break;

        int closeBracket = trimmed.Find(L"]", qNumPos);
        if (closeBracket < 0) break;

        CString qNumText = trimmed.Mid(qNumPos, closeBracket - qNumPos);
        qNumText.Trim();
        int qNum = _wtoi(qNumText);
        if (qNum <= 0) {
            scanPos = closeBracket + 1;
            continue;
        }
        if (qNum <= m_interviewQuestionCount) {
            scanPos = closeBracket + 1;
            continue;
        }

        int lineEnd = trimmed.Find(L"\n", marker);
        CString oneQuestion = (lineEnd >= 0) ? trimmed.Mid(marker, lineEnd - marker) : trimmed.Mid(marker);
        oneQuestion.Trim();

        m_interviewQuestionCount = qNum;

        CString prompt = oneQuestion;
        CString qGuide;
        qGuide.Format(L"\r\n\r\n[질문 %d] 예=\"예\", 아니요=\"아니요\"를 전송합니다.", m_interviewQuestionCount);
        prompt += qGuide;
        SetAgentStatus(L"입력 대기", L"인터뷰 질문에 예/아니요로 답변하세요.");

        int selected = MessageBox(prompt, L"Ouroboros 인터뷰 질문", MB_YESNO | MB_ICONQUESTION | MB_DEFBUTTON1);
        CString answer = (selected == IDYES) ? L"예" : L"아니요";

        bool childAlive = (m_running && m_childStdInWr && (!m_pi.hProcess || WaitForSingleObject(m_pi.hProcess, 0) == WAIT_TIMEOUT));

        AppendText(L"\r\n[DIALOG ANSWER Q" + CString(std::to_wstring(m_interviewQuestionCount).c_str()) + L"] " + answer + L"\r\n");
        if (!childAlive) {
            AppendText(L"[INFO] child 종료 상태라 자동전송은 생략합니다.\r\n");
        }
        else {
            SetAgentStatus(L"답변 전송 중", L"선택한 인터뷰 답변을 child process로 전송합니다.");
            DWORD writeErr = ERROR_SUCCESS;
            if (!WriteAnswer(answer, &writeErr)) {
                if (writeErr == ERROR_BROKEN_PIPE || writeErr == ERROR_INVALID_HANDLE) {
                    AppendText(L"[INFO] Dialog 응답 자동전송 생략: child stdin closed\r\n");
                }
                else {
                    CString detail = FormatWin32Error(writeErr);
                    AppendText(L"[WARN] Dialog 답변 자동전송 실패: " + detail + L"\r\n");
                    MessageBox(L"Dialog 답변 전송에 실패했습니다. Send 버튼으로 수동 전송해주세요.\r\n" + detail,
                        L"전송 실패", MB_ICONWARNING);
                }
            }
        }

        scanPos = (lineEnd >= 0) ? (lineEnd + 1) : (qNumPos + 1);
    }

    int finalMarker = trimmed.Find(L"[FINAL_CONFIRM_Q]");
    if (finalMarker >= 0 && !m_finalInputPromptShown) {
        m_finalInputPromptShown = true;

        int lineEnd = trimmed.Find(L"\n", finalMarker);
        CString finalQuestion = (lineEnd >= 0) ? trimmed.Mid(finalMarker, lineEnd - finalMarker) : trimmed.Mid(finalMarker);
        finalQuestion.Trim();
        CString prompt = finalQuestion;
        prompt += L"\r\n\r\n[최종 진단 확정]\r\n"
                  L"예: approved(확정 저장)\r\n"
                  L"아니요: rejected(반려, 확정 이력 미저장)\r\n"
                  L"취소: pending(보류, 감사 로그만 저장)";
        SetAgentStatus(L"최종확정 대기", L"최종 진단 확정 여부를 선택하세요.");

        int selected = MessageBox(prompt, L"최종 진단 확정", MB_YESNOCANCEL | MB_ICONQUESTION | MB_DEFBUTTON1);
        CString answer;
        if (selected == IDYES) {
            answer = L"approved";
        }
        else if (selected == IDNO) {
            answer = L"rejected";
        }
        else {
            answer = L"pending";
        }

        AppendText(L"\r\n[DIALOG FINAL_CONFIRM] " + answer + L"\r\n");
        SetAgentStatus(L"답변 전송 중", L"최종확정 응답을 child process로 전송합니다.");
        DWORD writeErr = ERROR_SUCCESS;
        if (!WriteAnswer(answer, &writeErr)) {
            if (writeErr == ERROR_BROKEN_PIPE || writeErr == ERROR_INVALID_HANDLE) {
                AppendText(L"[INFO] 최종확정 응답 자동전송 생략: child stdin closed\r\n");
            }
            else {
                CString detail = FormatWin32Error(writeErr);
                AppendText(L"[WARN] 최종확정 응답 자동전송 실패: " + detail + L"\r\n");
                MessageBox(L"최종확정 응답 전송에 실패했습니다. Send 버튼으로 수동 전송해주세요.\r\n" + detail,
                    L"전송 실패", MB_ICONWARNING);
            }
        }
    }
}

bool COrobrosTestDlg::SaveCsvPostprocess(const CString& fullOutput, CString& savedPath, CString& error)
{
    CString text = fullOutput;
    int start = text.Find(L"CSV_START");
    if (start < 0) {
        error = L"CSV_START 마커를 찾지 못했습니다.";
        return false;
    }

    int end = text.Find(L"CSV_END", start);
    if (end < 0) {
        error = L"CSV_END 마커를 찾지 못했습니다.";
        return false;
    }

    CString csv = text.Mid(start + 9, end - (start + 9));
    csv.Replace(L"\r\n", L"\n");
    csv.Replace(L"\r", L"\n");
    csv.Trim();
    if (csv.IsEmpty()) {
        error = L"CSV 본문이 비어 있습니다.";
        return false;
    }

    savedPath = L"C:\\Users\\yjs\\Desktop\\JAN\\Policy\\Data\\latest_features.csv";

    int bytesNeeded = WideCharToMultiByte(CP_UTF8, 0, csv, csv.GetLength(), nullptr, 0, nullptr, nullptr);
    if (bytesNeeded <= 0) {
        error = L"CSV 인코딩(UTF-8) 변환 실패";
        return false;
    }

    std::vector<char> bytes(static_cast<size_t>(bytesNeeded));
    WideCharToMultiByte(CP_UTF8, 0, csv, csv.GetLength(), bytes.data(), bytesNeeded, nullptr, nullptr);

    HANDLE hFile = CreateFileW(savedPath, GENERIC_WRITE, FILE_SHARE_READ, nullptr, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, nullptr);
    if (hFile == INVALID_HANDLE_VALUE) {
        error = L"CSV 파일 생성 실패: " + FormatWin32Error(GetLastError());
        return false;
    }

    DWORD written = 0;
    BOOL ok = WriteFile(hFile, bytes.data(), static_cast<DWORD>(bytes.size()), &written, nullptr);
    CloseHandle(hFile);

    if (!ok || written != bytes.size()) {
        error = L"CSV 파일 쓰기 실패";
        return false;
    }

    return true;
}

LRESULT COrobrosTestDlg::OnPipeOutput(WPARAM, LPARAM lParam)
{
    std::unique_ptr<CString> text(reinterpret_cast<CString*>(lParam));
    AppendText(*text);
    m_capturedOutput += *text;
    UpdateCurrentAgentFromOutput(*text);
    if (text->Find(L"[INTERVIEW_Q") >= 0) {
        SetAgentStatus(L"입력 대기", L"인터뷰 질문을 표시하는 중입니다.");
    }
    else if (text->Find(L"[FINAL_CONFIRM_Q]") >= 0) {
        SetAgentStatus(L"최종확정 대기", L"최종 진단 확정 질문을 표시하는 중입니다.");
    }
    else if (text->Find(L"[RUN]") >= 0) {
        SetAgentStatus(L"확인 중", L"필요한 파일과 로그를 확인하고 있습니다.");
    }
    else if (m_running) {
        SetAgentStatus(L"실행 중", L"agent가 요청을 처리하고 있습니다.");
    }
    MaybeShowQuestionDialog(*text);
    return 0;
}

LRESULT COrobrosTestDlg::OnProcessExited(WPARAM, LPARAM)
{
    DWORD exitCode = 0;
    bool haveExitCode = false;
    if (m_pi.hProcess) {
        WaitForSingleObject(m_pi.hProcess, 2000);
        haveExitCode = GetExitCodeProcess(m_pi.hProcess, &exitCode);
        if (haveExitCode && exitCode == STILL_ACTIVE) {
            haveExitCode = false;
        }
    }

    m_running = false;
    m_startButton.EnableWindow(TRUE);
    m_sendButton.EnableWindow(FALSE);
    m_stopButton.EnableWindow(FALSE);

    if (m_readerThread.joinable() && m_readerThread.get_id() != std::this_thread::get_id()) {
        m_readerThread.join();
    }

    if (m_childStdInWr) { CloseHandle(m_childStdInWr); m_childStdInWr = nullptr; }
    if (m_childStdOutRd) { CloseHandle(m_childStdOutRd); m_childStdOutRd = nullptr; }
    if (m_pi.hThread) { CloseHandle(m_pi.hThread); m_pi.hThread = nullptr; }
    if (m_pi.hProcess) { CloseHandle(m_pi.hProcess); m_pi.hProcess = nullptr; }

    CString msg;
    if (haveExitCode) {
        msg.Format(L"\r\n[Process exited or pipe closed] exit code=%lu\r\n", exitCode);
        if (exitCode == 0) {
            SetAgentStatus(L"완료", L"agent 작업이 정상 종료되었습니다.");
        }
        else {
            CString detail;
            detail.Format(L"agent 작업이 오류 종료되었습니다. exit code=%lu", exitCode);
            SetAgentStatus(L"오류", detail);
        }
    }
    else {
        msg = L"\r\n[Process exited or pipe closed]\r\n";
        SetAgentStatus(L"완료", L"pipe가 닫혀 agent 작업이 종료되었습니다.");
    }
    AppendText(msg);

    if (m_capturedOutput.Find(L"CSV_START") >= 0 && m_capturedOutput.Find(L"CSV_END") >= 0) {
        CString savedPath;
        CString saveError;
        if (SaveCsvPostprocess(m_capturedOutput, savedPath, saveError)) {
            AppendText(L"[CSV SAVED] " + savedPath + L"\r\n");
        }
        else {
            AppendText(L"[CSV SAVE SKIPPED] " + saveError + L"\r\n");
        }
    }

    AppendText(L"[INFO] Send 버튼은 실행 중인 child process에만 활성화됩니다. Start 직후 꺼졌다면 transcript의 오류/종료 메시지를 확인하세요.\r\n");
    return 0;
}

void COrobrosTestDlg::OnBnClickedStart()
{
    if (m_running) return;
    CString cmd = BuildCommandLine();
    m_capturedOutput.Empty();
    m_currentAgentName = DefaultAgentName();
    m_agentProgressList.DeleteAllItems();
    m_agentProgressSeq = 0;
    m_lastAgentStatusText.Empty();
    m_interviewQuestionCount = 0;
    m_finalInputPromptShown = false;
    AppendText(L"\r\n[START] ");
    AppendText(cmd + L"\r\n");
    SetAgentStatus(L"시작 중", L"6-agent diagnostic workflow child process를 생성하고 있습니다.");
    if (!StartProcess(cmd)) {
        DWORD err = GetLastError();
        CString msg;
        msg.Format(L"프로세스 실행 실패. %s\r\n", FormatWin32Error(err).GetString());
        SetAgentStatus(L"오류", L"프로세스 실행 실패");
        AppendText(msg);
        MessageBox(msg, L"실행 실패", MB_ICONERROR);
        return;
    }
    m_startButton.EnableWindow(FALSE);
    m_sendButton.EnableWindow(TRUE);
    m_stopButton.EnableWindow(TRUE);
}

void COrobrosTestDlg::OnBnClickedSend()
{
    CString answer;
    m_answerEdit.GetWindowText(answer);
    answer.Trim();
    if (answer.IsEmpty()) return;
    SetAgentStatus(L"답변 전송 중", L"입력한 답변을 child process로 전송합니다.");
    AppendText(L"\r\n[USER] " + answer + L"\r\n");
    DWORD writeErr = ERROR_SUCCESS;
    if (!WriteAnswer(answer, &writeErr)) {
        SetAgentStatus(L"오류", L"stdin pipe로 답변 전송 실패");
        MessageBox(L"stdin pipe로 답변 전송 실패\r\n" + FormatWin32Error(writeErr), L"전송 실패", MB_ICONERROR);
    }
    else {
        SetAgentStatus(L"실행 중", L"답변 전송 후 agent 처리를 기다리고 있습니다.");
    }
    m_answerEdit.SetWindowText(L"");
}

void COrobrosTestDlg::OnBnClickedStop()
{
    StopProcess();
}

void COrobrosTestDlg::OnBnClickedLoadLog()
{
    CFileDialog dlg(
        TRUE,
        L"txt",
        nullptr,
        OFN_FILEMUSTEXIST | OFN_PATHMUSTEXIST,
        L"Log Files (*.txt;*.TXT)|*.txt;*.TXT|All Files (*.*)|*.*||",
        this);

    dlg.m_ofn.lpstrInitialDir = L"C:\\Users\\yjs\\Desktop\\JAN\\LOG";

    if (dlg.DoModal() != IDOK) {
        return;
    }

    m_selectedLogPath = dlg.GetPathName();
    SetAgentStatus(L"로그 선택됨", L"선택한 로그를 command에 반영하고 있습니다.");

    CString command;
    m_commandEdit.GetWindowText(command);
    command.Trim();
    if (command.Find(L"run_maintenance_with_review.py") < 0) {
        command = DefaultMaintenanceCommand();
        AppendText(L"[WARN] command가 정비보고서 기본 실행기가 아니어서 기본 command로 복구했습니다.\r\n");
    }
    command = UpdateFocusLogArg(command, m_selectedLogPath);
    m_commandEdit.SetWindowText(command);

    AppendText(L"\r\n[LOG SELECTED] " + m_selectedLogPath + L"\r\n");

    CString preview = LoadLogPreview(m_selectedLogPath);
    if (preview.IsEmpty()) {
        AppendText(L"[WARN] 로그 미리보기를 읽지 못했습니다. 파일 경로만 반영했습니다.\r\n");
    }
    else {
        if (preview.GetLength() > 400) {
            preview = preview.Left(400) + L"...";
        }
        AppendText(L"[LOG PREVIEW]\r\n" + preview + L"\r\n");
    }
}

void COrobrosTestDlg::StopProcess()
{
    SetAgentStatus(L"중지 중", L"실행 중인 agent process를 종료하고 있습니다.");
    if (m_pi.hProcess) TerminateProcess(m_pi.hProcess, 1);
    m_running = false;
    if (m_childStdOutRd) { CloseHandle(m_childStdOutRd); m_childStdOutRd = nullptr; }
    if (m_readerThread.joinable()) m_readerThread.join();
    CloseProcessHandles();
}

void COrobrosTestDlg::CloseProcessHandles()
{
    if (m_childStdInWr) { CloseHandle(m_childStdInWr); m_childStdInWr = nullptr; }
    if (m_childStdInRd) { CloseHandle(m_childStdInRd); m_childStdInRd = nullptr; }
    if (m_childStdOutWr) { CloseHandle(m_childStdOutWr); m_childStdOutWr = nullptr; }
    if (m_childStdOutRd) { CloseHandle(m_childStdOutRd); m_childStdOutRd = nullptr; }
    if (m_pi.hThread) { CloseHandle(m_pi.hThread); m_pi.hThread = nullptr; }
    if (m_pi.hProcess) { CloseHandle(m_pi.hProcess); m_pi.hProcess = nullptr; }
}
