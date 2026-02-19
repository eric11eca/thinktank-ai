import { MessagesSquare } from "lucide-react";
import { Link, useLocation } from "react-router";

import {
  SidebarGroup,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from "@/components/ui/sidebar";
import { useI18n } from "@/core/i18n/hooks";

export function WorkspaceNavChatList() {
  const { t } = useI18n();
  const location = useLocation();
  return (
    <SidebarGroup className="pt-1">
      <SidebarMenu>
        <SidebarMenuItem>
          <SidebarMenuButton isActive={location.pathname === "/workspace/chats"} asChild>
            <Link className="text-muted-foreground" to="/workspace/chats">
              <MessagesSquare />
              <span>{t.sidebar.chats}</span>
            </Link>
          </SidebarMenuButton>
        </SidebarMenuItem>
      </SidebarMenu>
    </SidebarGroup>
  );
}
