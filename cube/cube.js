const EykApiClient = require('./eykApiClient');

const EYK_API_BASE_URL = 'http://eyk-django-api:5000';
const EYK_API_USERNAME = 'tech+cube@eykdata.com';
const EYK_API_PASSWORD = 'Test1234!';

const apiClient = new EykApiClient(EYK_API_BASE_URL, EYK_API_USERNAME, EYK_API_PASSWORD);

const getServiceAccountForConnection = async (connectionId) => {
  return await apiClient.getServiceAccount(connectionId);
};

// Cache for scheduler contexts - used as fallback for schema compilation
let cachedSchedulerContexts = null;

// Load and cache scheduler contexts
const loadSchedulerContexts = async () => {
  try {
    const contexts = await apiClient.getSchedulerContexts();
    cachedSchedulerContexts = contexts;
    console.log(`Scheduler contexts loaded: ${contexts.length}`);
    return contexts;
  } catch (error) {
    console.error('Failed to load scheduler contexts:', error);
    return [];
  }
};

// Get a default context for schema compilation when no security context is provided
const getDefaultContext = () => {
  if (cachedSchedulerContexts && cachedSchedulerContexts.length > 0) {
    console.log('Using first scheduler context as default for schema compilation');
    return cachedSchedulerContexts[0];
  }
  return null;
};

module.exports = {

  driverFactory: async ({ securityContext }) => {
    console.log('DEBUG: Incoming Security Context:', JSON.stringify(securityContext));

    // Use provided security context or fall back to first scheduler context
    const context = securityContext?.connection ? securityContext : getDefaultContext();

    if (!context?.connection) {
      console.warn('No valid context available for driverFactory - schema compilation may fail');
      return null;
    }

    const service_account = await getServiceAccountForConnection(context.connection);
    return {
      type: 'bigquery',
      projectId: service_account.project_id,
      credentials: service_account,
      dataset: context.dataset,
    };
  },

  contextToAppId: ({ securityContext }) => {
    // Handle empty context during schema compilation
    const connectionId = securityContext?.connection || 'default';
    return `CUBE_APP_${connectionId}`;
  },

  contextToOrchestratorId: ({ securityContext }) => {
    // Isolate connection pools and pre-aggregations per tenant
    const connectionId = securityContext?.connection || 'default';
    const dataset = securityContext?.dataset || 'default';
    return `CUBE_ORCH_${connectionId}_${dataset}`;
  },

  scheduledRefreshContexts: async () => {
    return await loadSchedulerContexts();
  }

};
