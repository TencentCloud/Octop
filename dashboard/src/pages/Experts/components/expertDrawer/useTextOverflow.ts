import { useEffect, useRef, useState } from "react";

export function useTextOverflow<T extends HTMLElement>(
  text: string | undefined,
  className: string,
) {
  const ref = useRef<T>(null);
  const [overflow, setOverflow] = useState(false);

  useEffect(() => {
    const element = ref.current;
    if (!text || !element) return;

    const measure = () => {
      setOverflow(
        element.clientWidth > 0 && element.scrollWidth > element.clientWidth,
      );
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, [text, className]);

  return { ref, tooltip: overflow ? text : undefined };
}
