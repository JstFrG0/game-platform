// Retry only cold-start connection/proxy/unavailable errors. Invalid requests
// and missing endpoints must surface immediately instead of looping forever.
export async function retryCatalogStartup(task, {signal, wait=abortableDelay}={}) {
  const delays=[350,900];
  for (let attempt=0;;attempt++) {
    signal?.throwIfAborted();
    try { return await task(); }
    catch (error) {
      if (signal?.aborted || error.name==='AbortError' || attempt>=delays.length ||
          !(error instanceof TypeError || [502,503,504].includes(error.status))) throw error;
      await wait(delays[attempt],signal);
    }
  }
}

function abortableDelay(milliseconds,signal) {
  return new Promise((resolve,reject) => {
    if (signal?.aborted) { reject(signal.reason);return; }
    const abort=() => { clearTimeout(timer);reject(signal.reason); };
    const timer=setTimeout(() => { signal?.removeEventListener('abort',abort);resolve(); },milliseconds);
    signal?.addEventListener('abort',abort,{once:true});
  });
}
