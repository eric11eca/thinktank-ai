import { createContext, useContext, useState } from "react";

type RightPanelContextType = {
  open: boolean;
  setOpen: (open: boolean) => void;
};

const RightPanelContext = createContext<RightPanelContextType | null>(null);

export function RightPanelProvider({
  children,
}: {
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(true);
  return (
    <RightPanelContext.Provider value={{ open, setOpen }}>
      {children}
    </RightPanelContext.Provider>
  );
}

export function useRightPanel(): RightPanelContextType {
  const ctx = useContext(RightPanelContext);
  // Fallback for use outside provider
  if (!ctx) return { open: true, setOpen: () => {} };
  return ctx;
}
