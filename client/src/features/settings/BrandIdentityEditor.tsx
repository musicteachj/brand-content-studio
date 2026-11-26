import { useState } from "react";
import { useAuthStore } from "@/stores/auth";
import type { Workspace } from "@/types";
import { BrandIdentityForm } from "./BrandIdentityForm";
import { BrandIdentityView } from "./BrandIdentityView";

/** Settings → Brand identity (Phase 4b). Read-only by default; "Edit" reveals a
 *  form to edit the workspace's palette, fonts, voice, accent, and logo. The
 *  brand_profile PATCH replaces the profile whole, so Save sends the full
 *  profile (logo included). Disabled for the demo user (server also 403s). */
export function BrandIdentityEditor({ workspace }: { workspace: Workspace }) {
  const isDemo = useAuthStore((s) => s.user?.is_demo ?? false);
  const [editing, setEditing] = useState(false);

  if (!editing) {
    return (
      <BrandIdentityView workspace={workspace} canEdit={!isDemo} onEdit={() => setEditing(true)} />
    );
  }
  return (
    <BrandIdentityForm key={workspace.id} workspace={workspace} onDone={() => setEditing(false)} />
  );
}
