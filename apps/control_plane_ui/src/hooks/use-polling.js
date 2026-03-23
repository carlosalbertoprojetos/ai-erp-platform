export function usePolling(callback, intervalMs = 15000) {
  let timer = null;
  const run = async () => {
    await callback();
  };
  run();
  timer = window.setInterval(run, intervalMs);
  return () => {
    if (timer) {
      window.clearInterval(timer);
      timer = null;
    }
  };
}
