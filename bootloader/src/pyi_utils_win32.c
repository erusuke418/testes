/*
 * ****************************************************************************
 * Copyright (c) 2013-2023, PyInstaller Development Team.
 *
 * Distributed under the terms of the GNU General Public License (version 2
 * or later) with exception for distributing the bootloader.
 *
 * The full license is in the file COPYING.txt, distributed with this software.
 *
 * SPDX-License-Identifier: (GPL-2.0-or-later WITH Bootloader-exception)
 * ****************************************************************************
 */

/*
 * Utility functions. This file contains implementations that are specific
 * to Windows.
 */

#ifdef _WIN32


#include <windows.h>
#include <io.h> /* _get_osfhandle */
#include <process.h> /* _getpid */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sddl.h> /* ConvertStringSecurityDescriptorToSecurityDescriptorW */

/* PyInstaller headers. */
#include "pyi_utils.h"

#include "pyi_global.h"
#include "pyi_path.h"
#include "pyi_main.h"


/**********************************************************************\
 *                  Environment variable management                   *
\**********************************************************************/
char *
pyi_getenv(const char *variable)
{
    wchar_t *variable_w;
    wchar_t value[PYI_PATH_MAX];
    wchar_t expanded_value[PYI_PATH_MAX];
    DWORD rc;

    /* Convert the variable name from UTF-8 to wide-char */
    variable_w = pyi_win32_utf8_to_wcs(variable, NULL, 0);

    /* Retrieve environment variable */
    rc = GetEnvironmentVariableW(variable_w, value, PYI_PATH_MAX);
    if (rc >= PYI_PATH_MAX) {
        return NULL; /* Insufficient buffer size */
    }
    if (rc == 0) {
        return NULL; /* Variable unavailable */
    }

    /* Expand environment variables within the environment variable's
     * value */
    rc = ExpandEnvironmentStringsW(value, expanded_value, PYI_PATH_MAX);
    if (rc >= PYI_PATH_MAX) {
        return NULL; /* Insufficient buffer size */
    }
    if (rc == 0) {
        return NULL; /* Error during expansion */
    }

    /* Convert to UTF-8 and return */
    return pyi_win32_wcs_to_utf8(expanded_value, NULL, 0);
}

int
pyi_setenv(const char *variable, const char *value)
{
    int rc;
    wchar_t *variable_w;
    wchar_t *value_w;

    /* Convert from UTF-8 to wide-char */
    variable_w = pyi_win32_utf8_to_wcs(variable, NULL, 0);
    value_w = pyi_win32_utf8_to_wcs(value, NULL, 0);

    /* `SetEnvironmentVariableW` updates only the value in the process
     * environment block, while _wputenv_s updates the value in the CRT
     * block AND calls `SetEnvironmentVariableW` to update the process
     * environment block.
     *
     * Therefore, in order for modification to be visible to other CRT
     * functions (for example, `_wtempnam`), we must use `_wputenv_s`. */
    rc = _wputenv_s(variable_w, value_w);

    free(variable_w);
    free(value_w);

    return rc;
}

int
pyi_unsetenv(const char *variable)
{
    int rc;
    wchar_t *variable_w;

    /* Convert from UTF-8 to wide-char */
    variable_w = pyi_win32_utf8_to_wcs(variable, NULL, 0);

    /* See the comment in `pyi_setenv`. As per MSDN, "You can remove a
     * variable from the environment by specifying an empty string (that
     * is, "") for value_string. */
    rc = _wputenv_s(variable_w, L"");

    free(variable_w);

    return rc;
}


/**********************************************************************\
 *         Temporary application top-level directory (onefile)        *
\**********************************************************************/
/* Resolve the temporary directory specified by user via runtime_tmpdir
 * option, and create corresponding directory tree. */
static wchar_t *
_pyi_create_runtime_tmpdir(const char *runtime_tmpdir)
{
    wchar_t *runtime_tmpdir_w;
    wchar_t runtime_tmpdir_expanded[PYI_PATH_MAX];
    wchar_t *runtime_tmpdir_abspath;
    wchar_t *subpath_cursor;
    wchar_t directory_tree_path[PYI_PATH_MAX];
    DWORD rc;

    /* Convert UTF-8 path to wide-char */
    runtime_tmpdir_w = pyi_win32_utf8_to_wcs(runtime_tmpdir, NULL, 0);
    if (!runtime_tmpdir_w) {
        FATALERROR("LOADER: failed to convert runtime-tmpdir to a wide string.\n");
        return NULL;
    }

    /* Expand environment variables like %LOCALAPPDATA% */
    rc = ExpandEnvironmentStringsW(runtime_tmpdir_w, runtime_tmpdir_expanded, PYI_PATH_MAX);
    free(runtime_tmpdir_w);
    if (!rc) {
        FATALERROR("LOADER: failed to expand environment variables in the runtime-tmpdir.\n");
        return NULL;
    }

    /* Resolve absolute path */
    if (pyi_win32_is_drive_root(runtime_tmpdir_expanded)) {
        /* Disk drive (e.g., "c:"); do not attempt to resolve full path
         * using _wfullpath(), because it will return the current directory
         * on the current drive. We also have no path to create. So just
         * return a verbatim copy of the string. */
        VS("LOADER: expanded runtime-tmpdir is a drive root: %ls\n", runtime_tmpdir_expanded);
        return _wcsdup(runtime_tmpdir_expanded);
    }

    runtime_tmpdir_abspath = _wfullpath(NULL, runtime_tmpdir_expanded, PYI_PATH_MAX);
    if (!runtime_tmpdir_abspath) {
        FATALERROR("LOADER: failed to obtain the absolute path of the runtime-tmpdir.\n");
        return NULL;
    }

    VS("LOADER: absolute runtime-tmpdir is %ls\n", runtime_tmpdir_abspath);

    /* Recursively create the directory structure
     *
     * NOTE: we call CreateDirectoryW without security descriptor for
     * this part of directory tree, as it might be shared by application
     * instances ran by different users. Only the last component (the
     * actual _MEIXXXXXX directory), created by the caller, uses security
     * descriptor to restrict access to current user.
     *
     * NOTE2: we ignore errors returned by CreateDirectoryW; if we
     * actually fail to create (a part of) directory tree here, we will
     * catch the error in the caller when trying to create the final
     * temporary directory component  (the actual _MEIXXXXXX directory).
     */
    for(subpath_cursor = wcschr(runtime_tmpdir_abspath, L'\\'); subpath_cursor != NULL; subpath_cursor = wcschr(++subpath_cursor, L'\\')) {
        int subpath_length = (int)(subpath_cursor - runtime_tmpdir_abspath);

        _snwprintf(directory_tree_path, PYI_PATH_MAX, L"%.*s", subpath_length, runtime_tmpdir_abspath);
        VS("LOADER: creating runtime-tmpdir path component: %ls\n", directory_tree_path);
        CreateDirectoryW(directory_tree_path, NULL);
    }

    /* Run once more on full path, to handle cases when path did not end
     * with separator. */
    VS("LOADER: creating runtime-tmpdir path: %ls\n", runtime_tmpdir_abspath);
    CreateDirectoryW(runtime_tmpdir_abspath, NULL);

    return runtime_tmpdir_abspath;
}

int
pyi_create_temporary_application_directory(PYI_CONTEXT *pyi_ctx)
{
    char *original_tmp_value = NULL;
    wchar_t prefix[16];
    wchar_t tempdir_path[PYI_PATH_MAX];
    int ret = 0;
    int i;

    /* If user specified the temporary directory via runtime_tmpdir
     * option, resolve it, create it, and store the path to TMP
     * environment variable to have`GetTempPathW` use it. */
    if (pyi_ctx->runtime_tmpdir != NULL) {
        wchar_t *runtime_tmpdir_w;
        DWORD rc;

        /* Retrieve original value of TMP environment variable, so we
         * can restore it at the very end of this function. */
        original_tmp_value = pyi_getenv("TMP");

        /* Resolve and create directory specified via the runtime_tmpdir
         * option. */
        runtime_tmpdir_w = _pyi_create_runtime_tmpdir(pyi_ctx->runtime_tmpdir);
        if (runtime_tmpdir_w == NULL) {
            free(original_tmp_value);
            return -1;
        }

        /* Store the path in the TMP environment variable. */
        rc = _wputenv_s(L"TMP", runtime_tmpdir_w);
        free(runtime_tmpdir_w);
        if (rc) {
            FATALERROR("LOADER: failed to set the TMP environment variable.\n");
            free(original_tmp_value);
            return -1;
        }

        VS("LOADER: successfully resolved the specified runtime-tmpdir\n");
    }

    /* Retrieve temporary directory */
    GetTempPathW(PYI_PATH_MAX, tempdir_path);

    /* Create _MEI + PID prefix */
    swprintf(prefix, 16, L"_MEI%d", _getpid());

    /* Windows does not have a race-free function to create a temporary
     * directory. Thus, we rely on _tempnam, and simply try several times
     * to avoid stupid race conditions. */
    for (i = 0; i < 5; i++) {
        wchar_t *application_home_dir_w = _wtempnam(tempdir_path, prefix);

        /* Try creating the directory. Use `CreateDirectoryW` with security
         * descriptor to limit access to current user. The functon returns
         * 0 on failure. */
        if (CreateDirectoryW(application_home_dir_w, pyi_ctx->security_attr) == 0) {
            free(application_home_dir_w);
            ret = -1; /* In case we reached max. retries */
        } else {
            /* Convert path to UTF-8 and store it in main context structure */
            if (pyi_win32_wcs_to_utf8(application_home_dir_w, pyi_ctx->application_home_dir, PYI_PATH_MAX) == NULL) {
                FATALERROR("LOADER: length of teporary directory path exceeds maximum path length!\n");
                ret = -1;
            }
            free(application_home_dir_w);
            break;
        }
    }

    /* If we modified TMP environment variable due to runtime_tmpdir
     * option, restore the environment variable to its original state. */
    if (pyi_ctx->runtime_tmpdir != NULL) {
        if (original_tmp_value!= NULL) {
            pyi_setenv("TMP", original_tmp_value);
            free(original_tmp_value);
        } else {
            pyi_unsetenv("TMP");
        }
    }

    return ret;
}


/**********************************************************************\
 *                  Recursive removal of a directory                  *
\**********************************************************************/
/* The actual implementation with wide-char path */
static int
_pyi_recursive_rmdir(const wchar_t *dir_path)
{
    int dir_path_length;
    int buffer_size;
    wchar_t entry_path[PYI_PATH_MAX];
    HANDLE handle;
    WIN32_FIND_DATAW entry_info;

    /* Copy the directory path, and append separator and a wildcard for
     * the `FindFirstFileW()` call. Store the length of the directory
     * path plus the separator; this allows us to re-use the same buffer
     * for constructing entries' full paths, by overwriting only the
     * part of the string that follows the path separator that we added. */
    dir_path_length = _snwprintf(entry_path, PYI_PATH_MAX, L"%s\\*", dir_path);
    if (dir_path_length >= PYI_PATH_MAX) {
        return -1;
    }
    dir_path_length--; /* Ignore the wildcard at the end */
    buffer_size = PYI_PATH_MAX - dir_path_length; /* Remaining buffer size */

    /* Start the search by looking for first entry */
    handle = FindFirstFileW(entry_path, &entry_info);
    if (handle == INVALID_HANDLE_VALUE) {
        return -1;
    }

    do {
        /* Skip . and .. */
        if (wcscmp(entry_info.cFileName, L".") == 0 || wcscmp(entry_info.cFileName, L"..") == 0) {
            continue;
        }

        /* Construct the full path, by overwriting the part of string
         * that starts after path directory and separator. */
        if (_snwprintf(entry_path + dir_path_length, buffer_size, L"%s", entry_info.cFileName) >= buffer_size) {
            continue;
        }

        /* Deteremine the type of entry, and remove it. Ignore errors
         * here - if we fail to  remove an entry here, we will also fail
         * to remove the top-level directory.*/
        if (entry_info.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) {
            /* Avoid recursing into symlinked directories */
            unsigned char is_symlink = 0;

            if (entry_info.dwFileAttributes & FILE_ATTRIBUTE_REPARSE_POINT) {
                if (entry_info.dwReserved0 == IO_REPARSE_TAG_SYMLINK) {
                    is_symlink = 1;
                }
            }

            if (is_symlink) {
                /* Remove only the symlink itself */
                RemoveDirectoryW(entry_path);
            } else {
                /* Recurse into directory */
                _pyi_recursive_rmdir(entry_path);
            }
        } else {
            /* Delete file (or symlink to a file) */
            DeleteFileW(entry_path);
        }
    } while (FindNextFileW(handle, &entry_info) != 0);

    FindClose(handle);

    /* Finally, remove the directory */
    return RemoveDirectoryW(dir_path) != 1 ? -1 : 0; /* false/true-> -1/0 */
}


/* For now, the caller is supplying narrow-char path in  UTF-8 encoding. */
int
pyi_recursive_rmdir(const char *dir_path)
{
    wchar_t dir_path_w[PYI_PATH_MAX];
    pyi_win32_utf8_to_wcs(dir_path, dir_path_w, PYI_PATH_MAX);
    return _pyi_recursive_rmdir(dir_path_w);
}


/**********************************************************************\
 *                  Shared library loading/unloading                  *
\**********************************************************************/
/* Load shared/dynamic library */
pyi_dylib_t
pyi_utils_dlopen(const char *filename)
{
    wchar_t *filename_w;
    pyi_dylib_t handle;

    /* Convert UTF-8 to wide-char */
    filename_w = pyi_win32_utf8_to_wcs(filename, NULL, 0);

    /* Load shared library */
    handle = LoadLibraryExW(filename_w, NULL, LOAD_WITH_ALTERED_SEARCH_PATH);

    free(filename_w);

    return handle;
}

/* Unload shared library by closing its handle */
int
pyi_utils_dlclose(pyi_dylib_t handle)
{
    return FreeLibrary(handle) ? 0 : -1; /* true/false -> 0/-1 */
}


/**********************************************************************\
 *                  Child process spawning (onefile)                  *
\**********************************************************************/
static BOOL WINAPI
_pyi_win32_console_ctrl(DWORD dwCtrlType)
{
    /* Due to different handling of VS() macro in MSVC and mingw gcc, the
     * former requires the name variable below to be available even in
     * non-debug builds (where VS() is no-op), while the latter complains
     * about the unused variable. So put everything under ifdef guard to
     * appease both. */
#if defined(LAUNCH_DEBUG)
    /* https://docs.microsoft.com/en-us/windows/console/handlerroutine */
    static const char *name_map[] = {
        "CTRL_C_EVENT", // 0
        "CTRL_BREAK_EVENT", // 1
        "CTRL_CLOSE_EVENT", // 2
        NULL,
        NULL,
        "CTRL_LOGOFF_EVENT", // 5
        "CTRL_SHUTDOWN_EVENT" // 6
    };
    const char *name = (dwCtrlType >= 0 && dwCtrlType <= 6) ? name_map[dwCtrlType] : NULL;

    /* NOTE: in case of CTRL_CLOSE_EVENT, CTRL_LOGOFF_EVENT, or
     * CTRL_SHUTDOWN_EVENT, the following message may not be printed to
     * console anymore. As per MSDN, the internal console cleanup routine
     * might have already been executed, preventing console functions
     * from working reliably. See Remarks section at:
     * https://docs.microsoft.com/en-us/windows/console/setconsolectrlhandler */
    VS("LOADER: received console control signal %d (%s)!\n", dwCtrlType, name ? name : "unknown");
#endif /* defined(LAUNCH_DEBUG) */

    /* Handle Ctrl+C and Ctrl+Break signals immediately. By returning TRUE,
     * their default handlers (which would call ExitProcess()) are not
     * called, so we are effectively suppressing the signal here, while
     * letting the child process (who also received it) handle it as they
     * see it fit. */
    if (dwCtrlType == CTRL_C_EVENT || dwCtrlType == CTRL_BREAK_EVENT) {
        return TRUE;
    }

    /* Delay the inevitable for as long as we can. The same signal should
     * also be received by the child process (as it is in the same process
     * group as the parent), which will terminate (after optionally
     * processing the signal, if python code installed its own handler).
     * Therefore, we just wait here "forever" (compared to OS-imposed
     * timeout for signal handling) to buy time for the child process to
     * terminate and for the main thread of this (parent) process to
     * perform the cleanup (sidenote: this handler is executed in a
     * separate thread). So this thread is terminated either when the
     * main thread of the process finishes and the program exits
     * (gracefully), or when the time runs out and the OS kills everything (see
     * https://docs.microsoft.com/en-us/windows/console/handlerroutine#timeouts). */
    Sleep(20000);
    return TRUE;
}

static HANDLE
_pyi_get_stream_handle(FILE *stream)
{
    HANDLE handle = (void *)_get_osfhandle(fileno(stream));
    /* When stdin, stdout, and stderr are not associated with a stream
     * (e.g., Windows application without console), _fileno() returns
     * special value -2. Therefore, call to _get_osfhandle() returns
     * INVALID_HANDLE_VALUE. If we caled _get_osfhandle() with 0, 1, or 2
     * instead of the result of _fileno(), _get_osfhandle() would also
     * return -2 when the file descriptor is not associated with the
     * stream. But because we take the _fileno() route, we need to handle
     * only INVALID_HANDLE_VALUE (= -1).
     * See: https://learn.microsoft.com/en-us/cpp/c-runtime-library/reference/get-osfhandle */
    if (handle == INVALID_HANDLE_VALUE) {
        return NULL;
    }
    return handle;
}

int
pyi_utils_create_child(PYI_CONTEXT *pyi_ctx)
{
    SECURITY_ATTRIBUTES security_attributes;
    STARTUPINFOW startup_info;
    PROCESS_INFORMATION process_info;
    wchar_t executable_filename_w[PYI_PATH_MAX];
    bool succeeded;
    DWORD child_exitcode;

    /* TODO is there a replacement for this conversion or just use wchar_t everywhere? */
    /* Convert file name to wchar_t from utf8. */
    pyi_win32_utf8_to_wcs(pyi_ctx->executable_filename, executable_filename_w, PYI_PATH_MAX);

    /* Set up console ctrl handler; the call returns non-zero on success */
    if (SetConsoleCtrlHandler(_pyi_win32_console_ctrl, TRUE) == 0) {
        VS("LOADER: failed to install console ctrl handler!\n");
    }

    VS("LOADER: setting up to run child\n");

    security_attributes.nLength = sizeof(security_attributes);
    security_attributes.lpSecurityDescriptor = NULL;
    security_attributes.bInheritHandle = TRUE;

    GetStartupInfoW(&startup_info);
    startup_info.lpReserved = NULL;
    startup_info.lpDesktop = NULL;
    startup_info.lpTitle = NULL;
    startup_info.dwFlags = STARTF_USESTDHANDLES | STARTF_USESHOWWINDOW;
    startup_info.wShowWindow = SW_NORMAL;
    startup_info.hStdInput = _pyi_get_stream_handle(stdin);
    startup_info.hStdOutput = _pyi_get_stream_handle(stdout);
    startup_info.hStdError = _pyi_get_stream_handle(stderr);

    VS("LOADER: creating child process\n");

    succeeded = CreateProcessW(
        executable_filename_w, /* lpApplicationName */
        GetCommandLineW(), /* lpCommandLine */
        &security_attributes, /* lpProcessAttributes */
        NULL, /* lpThreadAttributes */
        TRUE, /* bInheritHandles */
        0, /* dwCreationFlags */
        NULL, /* lpEnvironment */
        NULL, /* lpCurrentDirectory */
        &startup_info, /* lpStartupInfo */
        &process_info /* lpProcessInformation */
    );
    if (succeeded) {
        VS("LOADER: waiting for child process to finish...\n");
        WaitForSingleObject(process_info.hProcess, INFINITE);
        GetExitCodeProcess(process_info.hProcess, &child_exitcode);
        return child_exitcode;
    }

    FATAL_WINERROR("CreateProcessW", "Failed to create child process!\n");
    return -1;
}


/**********************************************************************\
 *             Security descriptor for temporary directory            *
\**********************************************************************/
/* Retrieve the SID for the specified token information class from the current process.
 *
 * At the moment, TokenUser and TokenAppContainerSid are supported.
 *
 * Used in a compatibility work-around for wine, which at the time of writing
 * (version 5.0.2) does not properly support SID S-1-3-4 (directory owner),
 * and therefore user's actual SID must be used instead.
 *
 * Returns a copy of SID string on success, NULL on failure (or if the SID is unavailable
 * or zero-length). The returned string must be freed using LocalFree().
 */
static wchar_t *
_pyi_win32_get_sid(TOKEN_INFORMATION_CLASS token_information_class)
{
    HANDLE process_token = INVALID_HANDLE_VALUE;
    DWORD token_info_size = 0;
    void *token_info = NULL;
    wchar_t *sid = NULL;

    /* Get access token for the calling process */
    if (!OpenProcessToken(GetCurrentProcess(), TOKEN_QUERY, &process_token)) {
        goto cleanup;
    }

    /* Query buffer size and allocate buffer */
    if (!GetTokenInformation(process_token, token_information_class, NULL, 0, &token_info_size)) {
        if (GetLastError() != ERROR_INSUFFICIENT_BUFFER) {
            goto cleanup;
        }
    }
    if (token_info_size == 0) {
        /* As per MSDN, in the Microsoft implementation, if number or size is zero, calloc
         * returns a pointer to an allocated block of non-zero size. An attempt to read or
         * write through the returned pointer leads to undefined behavior. */
        goto cleanup;
    }
    token_info = calloc(1, token_info_size);
    if (!token_info) {
        goto cleanup;
    }

    /* Get token information */
    if (!GetTokenInformation(process_token, token_information_class, token_info, token_info_size, &token_info_size)) {
        goto cleanup;
    }

    /* Convert SID to string */
    switch (token_information_class)
    {
        case TokenUser: {
            PTOKEN_USER user_info = (PTOKEN_USER)token_info;
            ConvertSidToStringSidW(user_info->User.Sid, &sid);
            break;
        }
        case TokenAppContainerSid: {
            PTOKEN_APPCONTAINER_INFORMATION app_container_info = (PTOKEN_APPCONTAINER_INFORMATION)token_info;
            ConvertSidToStringSidW(app_container_info->TokenAppContainer, &sid);
            break;
        }
        default: {
            /* Unsupoorted token information class */
            break;
        }
    }

    // Cleanup
cleanup:
    free(token_info);
    if (process_token != INVALID_HANDLE_VALUE) {
        CloseHandle(process_token);
    }

    return sid;
}

/* Initialize security descriptor applied to application's temporary directory and its
 * sub-directories.
 */
SECURITY_ATTRIBUTES *
pyi_win32_initialize_security_descriptor()
{
    SECURITY_ATTRIBUTES *security_attr;
    LPVOID lpSecurityDescriptor;
    wchar_t *user_sid;
    wchar_t *app_container_sid;
    wchar_t security_descriptor_str[PYI_PATH_MAX];
    int ret;

    /* Resolve user's SID for compatibility with wine */
    user_sid = _pyi_win32_get_sid(TokenUser);

    /* If program is running within an AppContainer, the app container SID has to be added to
     * the DACL, otherwise our process will not have access to the temporary directory. */
    app_container_sid = _pyi_win32_get_sid(TokenAppContainerSid); /* NULL when not running in AppContainer */

    /* DACL descriptor D:dacl_flags(string_ace1)(string_ace2)
     * with ACE string:
     * ace_type;ace_flags;rights;object_guid;inherit_object_guid;account_sid;(resource_attribute)
     * - ace_type = SDDL_ACCESS_ALLOWED (A)
     * - rights = SDDL_FILE_ALL (FA)
     * - account_sid = current user (queried SID)
     */
    if (app_container_sid) {
        ret = _snwprintf(
            security_descriptor_str,
            PYI_PATH_MAX,
            L"D:(A;;FA;;;%s)(A;;FA;;;%s)",
            user_sid ? user_sid : L"S-1-3-4",
            app_container_sid);
    } else {
        ret = _snwprintf(
            security_descriptor_str,
            PYI_PATH_MAX,
            L"D:(A;;FA;;;%s)",
            user_sid ? user_sid : L"S-1-3-4");
    }

    LocalFree(user_sid); /* Must be freed using LocalFree() */
    LocalFree(app_container_sid); /* Must be freed using LocalFree() */

    if (ret >= PYI_PATH_MAX) {
        OTHERERROR("Security descriptor string length exceeds PYI_PATH_MAX!\n");
        return NULL;
    }

    /* Convert security descriptor string to security descriptor, and
     * store it in the SECURITY_ATTRIBUTES structure. */
    VS("LOADER: initializing security descriptor from string: %S\n", security_descriptor_str);
    ret = ConvertStringSecurityDescriptorToSecurityDescriptorW(
        security_descriptor_str,
        SDDL_REVISION_1,
        &lpSecurityDescriptor,
        NULL);
    if (ret == 0) {
        return NULL;
    }

    /* Allocate SECURITY_ATTRIBUTES and fill it in. */
    security_attr = calloc(1, sizeof(SECURITY_ATTRIBUTES));
    security_attr->nLength = sizeof(SECURITY_ATTRIBUTES);
    security_attr->bInheritHandle = FALSE;
    security_attr->lpSecurityDescriptor = lpSecurityDescriptor;

    return security_attr;
}

/* Free security descriptor applied to application's temporary directory and its
 * sub-directories.
 */
void
pyi_win32_free_security_descriptor(SECURITY_ATTRIBUTES **security_attr_ref)
{
    SECURITY_ATTRIBUTES *security_attr = *security_attr_ref;

    security_attr_ref = NULL;

    /* Free security descriptor */
    LocalFree(security_attr->lpSecurityDescriptor);

    /* Free the structure itself */
    free(security_attr);
}


/**********************************************************************\
 *      Console minimization/hiding (console-enabled build only)      *
\**********************************************************************/
#if !defined(WINDOWED)

/* Helper that hides or minimizes the console window if it is owned by
 * the process. The show_cmd argument is passed to the ShowWindow call,
 * and should be either SW_HIDE or SW_SHOWMINNOACTIVE.
 */
static void pyi_win32_adjust_console(int show_cmd)
{
    HWND hConsole = GetConsoleWindow();
    if (hConsole != NULL) {
        DWORD dwProcessId = GetCurrentProcessId();
        DWORD dwConsoleProcessId;

        if (GetWindowThreadProcessId(hConsole, &dwConsoleProcessId) == 0) {
            return; /* Window handle is invalid */
        }

        if (dwProcessId == dwConsoleProcessId) {
            ShowWindow(hConsole, show_cmd);
        }
    }
}

void pyi_win32_hide_console()
{
    pyi_win32_adjust_console(SW_HIDE);
}

void pyi_win32_minimize_console()
{
    pyi_win32_adjust_console(SW_SHOWMINNOACTIVE);
}

#endif /* !defined(WINDOWED) */


#endif /* ifdef _WIN32 */
