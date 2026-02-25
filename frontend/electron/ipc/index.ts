import { registerConfigHandlers } from "./config";
import { registerDialogHandlers } from "./dialogs";
import { registerUpdateHandlers } from "./update";
import { registerWindowHandlers } from "./window";

/**
 * Register all IPC handlers
 * Called once during app initialization
 */
export function registerIPCHandlers(): void {
  registerConfigHandlers();
  registerDialogHandlers();
  registerWindowHandlers();
  registerUpdateHandlers();
}
