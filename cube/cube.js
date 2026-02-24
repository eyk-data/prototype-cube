const defaultDataset = () => process.env.CUBEJS_BQ_DATASET || "";

module.exports = {
  scheduledRefreshContexts: async () => {
    const dataset = defaultDataset();
    if (!dataset) return [];
    return [{ securityContext: { dataset } }];
  },

  contextToAppId: ({ securityContext }) => {
    const dataset = securityContext?.dataset;
    if (!dataset) return undefined;
    return `CUBE_APP_${dataset}`;
  },

  contextToOrchestratorId: ({ securityContext }) => {
    const dataset = securityContext?.dataset;
    if (!dataset) return undefined;
    return `CUBE_APP_${dataset}`;
  },

  checkAuth: (req, authorization) => {
    const defaultDs = defaultDataset();
    if (!authorization || !authorization.startsWith("Bearer ")) {
      if (defaultDs) {
        req.securityContext = { dataset: defaultDs };
        req.authInfo = { securityContext: { dataset: defaultDs } };
      }
      return;
    }
  },

  extendContext: (req, context) => {
    const safeContext = context || {};
    const defaultDs = defaultDataset();
    const ctx = safeContext.securityContext || {};
    const dataset = (ctx.dataset || defaultDs || "").toString().trim();
    if (!dataset && defaultDs) {
      console.warn(
        "[Cube] extendContext: security context had no dataset, using CUBEJS_BQ_DATASET"
      );
    }
    return {
      ...safeContext,
      securityContext: { ...ctx, dataset: dataset || defaultDs },
    };
  },
};
