import { useLocation } from "react-router";
import { ThemeProvider as NextThemesProvider } from "next-themes";

export function ThemeProvider({
  children,
  ...props
}: React.ComponentProps<typeof NextThemesProvider>) {
  const location = useLocation();
  return (
    <NextThemesProvider
      {...props}
      forcedTheme={location.pathname === "/" ? "dark" : undefined}
    >
      {children}
    </NextThemesProvider>
  );
}
