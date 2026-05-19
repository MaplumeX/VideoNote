import { Form, useActionData, useNavigation, useSearchParams } from "react-router";
import { useTranslation } from "react-i18next";
import { setAccessToken } from "@/auth/token";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

interface ActionError {
  error: string;
}

export async function loginAction({ request }: { request: Request }) {
  const formData = await request.formData();
  const email = formData.get("email") as string;
  const password = formData.get("password") as string;

  const res = await fetch("/api/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ email, password }),
  });

  if (!res.ok) {
    const data = await res.json().catch(() => ({ detail: "Login failed" }));
    return { error: data.detail || "Invalid credentials" };
  }

  const data = await res.json();
  setAccessToken(data.access_token);

  const url = new URL(request.url);
  const redirectTo = url.searchParams.get("redirect") || "/app";
  return new Response(null, {
    status: 302,
    headers: { Location: redirectTo },
  });
}

export function LoginPage() {
  const { t } = useTranslation();
  const actionData = useActionData() as ActionError | undefined;
  const navigation = useNavigation();
  const [searchParams] = useSearchParams();
  const isSubmitting = navigation.state === "submitting";

  return (
    <div className="min-h-screen bg-background flex items-center justify-center px-4">
      <div className="w-full max-w-md space-y-6">
        <div className="text-center">
          <h1 className="text-2xl font-bold">VideoNote</h1>
          <p className="text-sm text-muted-foreground mt-1">{t("auth.signInSubtitle")}</p>
        </div>

        {actionData?.error && (
          <div className="rounded-lg bg-destructive/10 border border-destructive/20 px-4 py-3 text-sm text-destructive">
            {actionData.error}
          </div>
        )}

        <Form method="post" className="space-y-4">
          <div>
            <label htmlFor="email" className="block text-sm font-medium mb-1.5">
              {t("auth.email")}
            </label>
            <Input
              id="email"
              name="email"
              type="email"
              required
              autoComplete="email"
            />
          </div>
          <div>
            <label htmlFor="password" className="block text-sm font-medium mb-1.5">
              {t("auth.password")}
            </label>
            <Input
              id="password"
              name="password"
              type="password"
              required
              autoComplete="current-password"
            />
          </div>
          <Button
            type="submit"
            disabled={isSubmitting}
            className="w-full"
          >
            {isSubmitting ? t("auth.signingIn") : t("auth.signIn")}
          </Button>
        </Form>

        <p className="text-center text-sm text-muted-foreground">
          {t("auth.noAccount")}{" "}
          <a
            href={`/auth/register${searchParams.get("redirect") ? "?redirect=" + searchParams.get("redirect") : ""}`}
            className="text-primary hover:underline"
          >
            {t("auth.register")}
          </a>
        </p>
      </div>
    </div>
  );
}
