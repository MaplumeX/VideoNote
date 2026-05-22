import { useState, useCallback, useRef, createContext, useContext, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import {
  AlertDialog,
  AlertDialogContent,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogAction,
  AlertDialogCancel,
} from "@/components/ui/alert-dialog";

interface ConfirmState {
  title: string;
  description?: string;
  destructive?: boolean;
  resolve: (value: boolean) => void;
}

interface ConfirmContextValue {
  confirm: (options: {
    title: string;
    description?: string;
    destructive?: boolean;
  }) => Promise<boolean>;
}

const ConfirmContext = createContext<ConfirmContextValue>({
  confirm: () => Promise.resolve(false),
});

export function ConfirmProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<ConfirmState | null>(null);
  const resolveRef = useRef<((value: boolean) => void) | null>(null);
  const { t } = useTranslation();

  const confirm = useCallback(
    (options: {
      title: string;
      description?: string;
      destructive?: boolean;
    }): Promise<boolean> => {
      return new Promise<boolean>((resolve) => {
        resolveRef.current = resolve;
        setState({ ...options, resolve });
      });
    },
    [],
  );

  const handleClose = useCallback(
    (value: boolean) => {
      if (resolveRef.current) {
        resolveRef.current(value);
        resolveRef.current = null;
        setState(null);
      }
    },
    [],
  );

  return (
    <ConfirmContext.Provider value={{ confirm }}>
      {children}
      {state && (
        <AlertDialog open onOpenChange={(open) => { if (!open) handleClose(false); }}>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>{state.title}</AlertDialogTitle>
              {state.description && (
                <AlertDialogDescription>{state.description}</AlertDialogDescription>
              )}
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel onClick={() => handleClose(false)}>
                {t("confirm.cancel")}
              </AlertDialogCancel>
              <AlertDialogAction
                variant={state.destructive ? "destructive" : "default"}
                onClick={() => handleClose(true)}
              >
                {t("confirm.ok")}
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      )}
    </ConfirmContext.Provider>
  );
}

export function useConfirm() {
  return useContext(ConfirmContext);
}
