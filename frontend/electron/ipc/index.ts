import { registerConfigHandlers } from "./config";
import { registerDialogHandlers } from "./dialogs";
import { registerWindowHandlers } from "./window";
import { registerUpdateHandlers } from "./update";

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
