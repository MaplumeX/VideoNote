import { useCallback, useState } from "react";
import { translateApiError } from "../api/client";
import { silentRefresh } from "../auth/api";
import { getAccessToken } from "../auth/token";
import i18n from "../i18n";

interface UploadState {
  uploading: boolean;
  progress: number;
  jobId: string | null;
  error: string | null;
  errorCode: string | null;
}

function parseErrorCode(detail: unknown): string | null {
  if (typeof detail === "object" && detail !== null && "code" in detail) {
    const code = (detail as { code: string }).code;
    return typeof code === "string" ? code : null;
  }
  return null;
}

export function useVideoUpload() {
  const [state, setState] = useState<UploadState>({
    uploading: false,
    progress: 0,
    jobId: null,
    error: null,
    errorCode: null,
  });

  const upload = useCallback((file: File, language: string, accessToken?: string | null): Promise<string> => {
    return new Promise((resolve) => {
      setState({ uploading: true, progress: 0, jobId: null, error: null, errorCode: null });

      const formData = new FormData();
      formData.append("file", file);
      formData.append("language", language);

      // Start the XHR upload.
      const doUpload = (token: string | null | undefined, attemptedRefresh: boolean) => {
        const xhr = new XMLHttpRequest();

        xhr.upload.onprogress = (e) => {
          if (e.lengthComputable) {
            setState((prev) => ({ ...prev, progress: e.loaded / e.total }));
          }
        };

        xhr.onload = async () => {
          if (xhr.status >= 200 && xhr.status < 300) {
            const data = JSON.parse(xhr.responseText);
            setState((prev) => ({
              ...prev,
              uploading: false,
              progress: 1,
              jobId: data.job_id,
            }));
            resolve(data.job_id);
          } else if (xhr.status === 401) {
            // If we haven't attempted a refresh yet, try to restore the session
            // and automatically retry the upload with the new token.
            if (!attemptedRefresh) {
              const sessionRestored = await silentRefresh();
              if (sessionRestored) {
                setState((prev) => ({ ...prev, progress: 0 }));
                doUpload(getAccessToken(), true);
                return;
              }
            }
            setState({
              uploading: false,
              progress: 0,
              jobId: null,
              error: i18n.t("errors.uploadSessionExpired"),
              errorCode: null,
            });
            resolve("");
          } else {
            let detail = i18n.t("errors.unknown");
            let code: string | null = null;
            try {
              const err = JSON.parse(xhr.responseText);
              detail = translateApiError(err.detail);
              code = parseErrorCode(err.detail);
            } catch {
              // use default message
            }
            setState({ uploading: false, progress: 0, jobId: null, error: detail, errorCode: code });
            resolve("");
          }
        };

        xhr.onerror = () => {
          setState({
            uploading: false,
            progress: 0,
            jobId: null,
            error: i18n.t("errors.uploadNetworkFailed"),
            errorCode: null,
          });
          resolve("");
        };

        xhr.open("POST", "/api/upload");
        if (token) {
          xhr.setRequestHeader("Authorization", `Bearer ${token}`);
        }
        xhr.send(formData);
      };

      doUpload(accessToken, false);
    });
  }, []);

  return { ...state, upload };
}