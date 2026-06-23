let authFailureHandler: (() => void) | null = null;

export function registerAuthFailureHandler(handler: () => void) {
  authFailureHandler = handler;
  return () => {
    if (authFailureHandler === handler) {
      authFailureHandler = null;
    }
  };
}

export function triggerAuthFailure() {
  if (authFailureHandler) {
    authFailureHandler();
  }
}
