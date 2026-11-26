import { useState, type FormEvent } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

/** Email and password sign-in, for local development only: the server closes it in
 *  production, and the pages hide it when GET /api/status says so. The parent owns the
 *  request (useAuthActions), its error, and the one-sign-in-at-a-time lock. */
export function PasswordSignInForm({
  onSubmit,
  loading,
  disabled,
  className,
}: {
  onSubmit: (email: string, password: string) => void;
  loading: boolean;
  disabled: boolean;
  className?: string;
}) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  function submit(e: FormEvent) {
    e.preventDefault();
    if (!disabled) onSubmit(email, password);
  }

  return (
    <form onSubmit={submit} className={cn("flex flex-col gap-4", className)} noValidate>
      <div className="flex flex-col gap-1.5">
        <label htmlFor="email" className="text-sm font-medium text-foreground">
          Email
        </label>
        <Input
          id="email"
          type="email"
          autoComplete="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="you@studio.com"
          required
        />
      </div>
      <div className="flex flex-col gap-1.5">
        <label htmlFor="password" className="text-sm font-medium text-foreground">
          Password
        </label>
        <Input
          id="password"
          type="password"
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
        />
      </div>
      <Button
        type="submit"
        variant="secondary"
        className="mt-1 w-full"
        loading={loading}
        disabled={disabled}
      >
        Sign in
      </Button>
    </form>
  );
}
