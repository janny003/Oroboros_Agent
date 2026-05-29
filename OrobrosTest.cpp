#include "framework.h"
#include "OrobrosTest.h"
#include "OrobrosTestDlg.h"
#ifdef _DEBUG
#define new DEBUG_NEW
#endif
COrobrosTestApp theApp;
BOOL COrobrosTestApp::InitInstance()
{
    CWinApp::InitInstance();
    INITCOMMONCONTROLSEX InitCtrls{};
    InitCtrls.dwSize = sizeof(InitCtrls);
    InitCtrls.dwICC = ICC_WIN95_CLASSES | ICC_LISTVIEW_CLASSES;
    InitCommonControlsEx(&InitCtrls);
    COrobrosTestDlg dlg;
    m_pMainWnd = &dlg;
    dlg.DoModal();
    return FALSE;
}
