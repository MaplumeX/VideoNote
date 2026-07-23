import { useCallback, useState } from "react";
import { translateApiError } from "../api/client";
import { silentRefresh } from "../auth/api";
import i18n from "../i18n";

interface UploadState {
  uploading: boolean;
  progress: number;
  jobId: string | null;
  error: string | null;
}

export function useVideoUpload() {
  const [state, setState] = useState<UploadState>({
    uploading: false,
    progress: 0,
    jobId: null,
    error: null,
  });

  const upload = useCallback((file: File, language: string, accessToken?: string | null): Promise<string> => {
    return new Promise((resolve) => {
      setState({ uploading: true, progress: 0, jobId: null, error: null });

      const formData = new FormData();
      formData.append("file", file);
      formData.append("language", language);

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
          const sessionRestored = await silentRefresh();
          setState({
            uploading: false,
            progress: 0,
            jobId: null,
            error: i18n.t(
              sessionRestored
                ? "errors.uploadSessionRefreshed"
                : "errors.uploadSessionExpired",
            ),
          });
          resolve("");
        } else {
          let detail = i18n.t("errors.unknown");
          try {
            const err = JSON.parse(xhr.responseText);
            detail = translateApiError(err.detail);
          } catch {
            // use default message
          }
          setState({ uploading: false, progress: 0, jobId: null, error: detail });
          resolve("");
        }
      };

      xhr.onerror = () => {
        setState({
          uploading: false,
          progress: 0,
          jobId: null,
          error: i18n.t("errors.uploadNetworkFailed"),
        });
        resolve("");
      };

      xhr.open("POST", "/api/upload");
      if (accessToken) {
        xhr.setRequestHeader("Authorization", `Bearer ${accessToken}`);
      }
      xhr.send(formData);
    });
  }, []);

  return { ...state, upload };
}
