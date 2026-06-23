import { setupServer } from "msw/node";
import { handlers as authHandlers } from "./handlers/auth";
import { handlers as resumeHandlers } from "./handlers/resume";
import { handlers as pathHandlers } from "./handlers/paths";
import { handlers as settingsHandlers } from "./handlers/settings";
import { handlers as knowledgeHandlers } from "./handlers/knowledge";
import { handlers as tasksHandlers } from "./handlers/tasks";

export const server = setupServer(
  ...authHandlers,
  ...resumeHandlers,
  ...pathHandlers,
  ...settingsHandlers,
  ...knowledgeHandlers,
  ...tasksHandlers
);
