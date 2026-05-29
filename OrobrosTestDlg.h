#pragma once
#include "framework.h"
#include "resource.h"

constexpr UINT WM_PIPE_OUTPUT = WM_APP + 101;
constexpr UINT WM_PROCESS_EXITED = WM_APP + 102;

class COrobrosTestDlg : public CDialogEx
{
public:
    COrobrosTestDlg(CWnd* pParent = nullptr);
    enum { IDD = IDD_OROBROSTEST_DIALOG };

protected:
    virtual void DoDataExchange(CDataExchange* pDX);
    virtual BOOL OnInitDialog();
    afx_msg void OnBnClickedStart();
    afx_msg void OnBnClickedSend();
    afx_msg void OnBnClickedStop();
    afx_msg void OnBnClickedLoadLog();
    afx_msg LRESULT OnPipeOutput(WPARAM wParam, LPARAM lParam);
    afx_msg LRESULT OnProcessExited(WPARAM wParam, LPARAM lParam);
    DECLARE_MESSAGE_MAP()

private:
    CEdit m_commandEdit;
    CEdit m_contextEdit;
    CEdit m_transcriptEdit;
    CEdit m_answerEdit;
    CButton m_startButton;
    CButton m_sendButton;
    CButton m_stopButton;
    CStatic m_agentStatusLabel;
    CStatic m_agentStatusText;
    CListCtrl m_agentProgressList;

    HANDLE m_childStdInRd = nullptr;
    HANDLE m_childStdInWr = nullptr;
    HANDLE m_childStdOutRd = nullptr;
    HANDLE m_childStdOutWr = nullptr;
    PROCESS_INFORMATION m_pi{};
    std::thread m_readerThread;
    std::atomic_bool m_running{ false };
    CString m_lastQuestionPopup;
    CString m_lastAgentStatusText;
    CString m_capturedOutput;
    CString m_currentAgentName;
    int m_agentProgressSeq = 0;
    CString m_selectedLogPath;
    int m_interviewQuestionCount = 0;
    bool m_finalInputPromptShown = false;

    void AppendText(const CString& text);
    bool StartProcess(const CString& commandLine);
    void StopProcess();
    void CloseProcessHandles();
    void ReaderLoop();
    bool WriteAnswer(const CString& answer, DWORD* lastError = nullptr);
    void SetAgentStatus(const CString& state, const CString& detail);
    void AddAgentProgress(const CString& state, const CString& detail);
    void InitializeAgentProgressList();
    void UpdateCurrentAgentFromOutput(const CString& chunk);
    static CString DefaultAgentName();
    static CString Utf8ToWide(const char* data, int len);
    static CString QuoteArg(const CString& s);
    static CString FormatWin32Error(DWORD error);
    static CString DefaultMaintenanceCommand();
    CString BuildCommandLine() const;
    void MaybeShowQuestionDialog(const CString& chunk);
    bool SaveCsvPostprocess(const CString& fullOutput, CString& savedPath, CString& error);
    static CString UpdateFocusLogArg(const CString& command, const CString& logPath);
    static CString LoadLogPreview(const CString& logPath, size_t maxBytes = 2048);
};
