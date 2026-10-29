// Restore only after the matching catalog has finished rendering.
export function createCatalogScroll() {
  const positions = new Map();
  let navigation = 0;
  let renderSignal;
  let requestedRestore;

  function restoreOnNextCatalog(path, position) {
    requestedRestore = { path, position: { ...position } };
  }

  function beforeNavigation(to, from, position) {
    navigation += 1;
    renderSignal?.resolve(false);
    renderSignal = undefined;
    if (from.name === "catalog") {
      positions.delete(from.fullPath);
      positions.set(from.fullPath, { ...position });
      if (positions.size > 50) positions.delete(positions.keys().next().value);
    }
    if (to.name === "catalog") {
      let resolve;
      const promise = new Promise((done) => { resolve = done; });
      renderSignal = {
        path: to.fullPath, promise, resolve,
        restore: requestedRestore?.path === to.fullPath
          ? requestedRestore.position : undefined,
      };
    }
    requestedRestore = undefined;
  }

  function catalogReady(path) {
    if (renderSignal?.path === path) renderSignal.resolve(true);
  }

  async function scrollBehavior(to, from, savedPosition) {
    if (to.name !== "catalog") return savedPosition ?? { left: 0, top: 0 };
    const target = renderSignal?.restore ?? savedPosition ??
      (from.name === "detail" ? positions.get(to.fullPath) : undefined);
    if (!target) return { left: 0, top: 0 };
    const current = navigation;
    const signal = renderSignal;
    if (!signal || signal.path !== to.fullPath) return false;
    const ready = await signal.promise;
    if (!ready || current !== navigation) return false;
    return { ...target, behavior: "instant" };
  }

  return { beforeNavigation, catalogReady, scrollBehavior, restoreOnNextCatalog };
}

export const catalogScroll = createCatalogScroll();
