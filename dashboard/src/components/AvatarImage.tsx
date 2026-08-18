import { useEffect, useState } from "react";

/**
 * Resolve a JWT-protected avatar URL (e.g. /api/avatars/users/me) into a
 * blob object URL. Returns null while loading or on failure — callers
 * render their existing fallback (initials / icon) in that case.
 */
export function useAvatarObjectUrl(
  avatarUrl: string | null | undefined,
): string | null {
  const [src, setSrc] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    let objectUrl: string | undefined;
    setSrc(null);

    if (!avatarUrl) return;

    (async () => {
      try {
        const { fetchAuthImageBlob } = await import("../hooks/useAuthImageSrc");
        const blob = await fetchAuthImageBlob(avatarUrl);
        if (cancelled) return;
        objectUrl = URL.createObjectURL(blob);
        setSrc(objectUrl);
      } catch {
        /* leave null — callers fall back to initials/icon */
      }
    })();

    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [avatarUrl]);

  return src;
}

/**
 * Authenticated <img> for JWT-protected avatar URLs; renders nothing until
 * loaded so the caller's fallback shows through underneath.
 */
export function AvatarImage({
  avatarUrl,
  alt = "",
  size,
  style,
}: {
  avatarUrl: string | null | undefined;
  alt?: string;
  size: number;
  style?: React.CSSProperties;
}) {
  const src = useAvatarObjectUrl(avatarUrl);
  if (!src) return null;
  return (
    <img
      src={src}
      alt={alt}
      width={size}
      height={size}
      style={{
        width: size,
        height: size,
        borderRadius: "50%",
        objectFit: "cover",
        ...style,
      }}
    />
  );
}
