import { useCallback, useState } from "react";

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

      xhr.onload = () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          const data = JSON.parse(xhr.responseText);
          setState((prev) => ({
            ...prev,
            uploading: false,
            progress: 1,
            jobId: data.job_id,
          }));
          resolve(data.job_id);
        } else {
          let detail = `Upload failed (HTTP ${xhr.status})`;
          try {
            const err = JSON.parse(xhr.responseText);
            detail = err.detail || detail;
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
          error: null,
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
