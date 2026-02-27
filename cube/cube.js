
const EYK_API_BASE_URL = 'http://eyk-django-api:5000';
const EYK_API_USERNAME = 'tech+cube@eykdata.com';
const EYK_API_PASSWORD = 'Test1234!';

class EykApiClient {
  constructor(baseUrl, username, password) {
    this.baseUrl = baseUrl;
    this.username = username;
    this.password = password;
    this.accessToken = null;
    this.tokenExpiry = null;
  }

  fetchWithTimeout(url, options = {}) {
    return fetch(url, {
      ...options,
      signal: AbortSignal.timeout(10000),
    });
  }

  decodeJWT(token) {
    const parts = token.split('.');
    if (parts.length !== 3) {
      throw new Error('Invalid JWT token format');
    }
    const payload = Buffer.from(parts[1], 'base64').toString('utf-8');
    return JSON.parse(payload);
  }

  async login() {
    const response = await this.fetchWithTimeout(
      `${this.baseUrl}/auth/jwt/create/`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          email: this.username,
          password: this.password,
        }),
      },
    );

    if (!response.ok) {
      throw new Error(`Login failed: ${response.status} ${await response.text()}`);
    }

    const data = await response.json();
    this.accessToken = data.access;

    try {
      const decoded = this.decodeJWT(this.accessToken);
      this.tokenExpiry = decoded.exp
        ? new Date(decoded.exp * 1000)
        : new Date(Date.now() + 15 * 60 * 1000);
    } catch (err) {
      console.warn(`Failed to decode JWT, using 15min default expiry: ${err.message}`);
      this.tokenExpiry = new Date(Date.now() + 15 * 60 * 1000);
    }

    console.log(`JWT token obtained, expires at ${this.tokenExpiry.toISOString()}`);
  }

  async ensureAuthenticated() {
    if (
      !this.accessToken ||
      !this.tokenExpiry ||
      Date.now() >= this.tokenExpiry.getTime() - 30000
    ) {
      await this.login();
    }
  }

  async authenticatedFetch(url, context) {
    await this.ensureAuthenticated();

    const doFetch = () =>
      this.fetchWithTimeout(url, {
        headers: { Authorization: `Bearer ${this.accessToken}` },
      });

    let response;
    try {
      response = await doFetch();
    } catch (err) {
      console.warn(`${context}: network error, retrying: ${err.message}`);
      response = await doFetch();
    }

    if (response.status === 401) {
      console.warn(`${context}: got 401, re-authenticating`);
      await this.login();
      response = await doFetch();
    }

    if (response.status >= 500) {
      console.warn(`${context}: got ${response.status}, retrying`);
      response = await doFetch();
    }

    if (!response.ok) {
      throw new Error(
        `${context}: ${response.status} ${await response.text()}`,
      );
    }

    return response.json();
  }

  async getSchedulerContexts() {
    return this.authenticatedFetch(
      `${this.baseUrl}/api/cube/config/refresh-contexts`,
      'Failed to get scheduler contexts',
    );
  }

  async getServiceAccount(connectionId) {
    return this.authenticatedFetch(
      `${this.baseUrl}/api/cube/config/${connectionId}/service-account`,
      'Failed to get service account',
    );
  }
}

const apiClient = new EykApiClient(
  EYK_API_BASE_URL,
  EYK_API_USERNAME,
  EYK_API_PASSWORD,
);

const CONTEXTS_TTL_MS = 5 * 60 * 1000;
let cachedContexts = null;
let contextsFetchedAt = 0;

async function getCachedContexts() {
  if (!cachedContexts || Date.now() - contextsFetchedAt > CONTEXTS_TTL_MS) {
    try {
      cachedContexts = await apiClient.getSchedulerContexts();
      contextsFetchedAt = Date.now();
    } catch (err) {
      if (cachedContexts) {
        console.warn(`Failed to refresh contexts, using stale cache: ${err.message}`);
        return cachedContexts;
      }
      throw err;
    }
  }
  return cachedContexts;
}

module.exports = {
  driverFactory: async ({ securityContext }) => {
    const contexts = await getCachedContexts();
    const fallback = contexts[0]?.securityContext;

    const connectionId = securityContext?.connection || fallback?.connection;

    if (!connectionId) {
      throw new Error(
        'No connectionId available: securityContext.connection is missing and no cached contexts found',
      );
    }

    const serviceAccount = await apiClient.getServiceAccount(connectionId);

    return {
      type: 'bigquery',
      projectId: serviceAccount.project_id,
      credentials: serviceAccount,
      dataset: securityContext?.dataset || fallback?.dataset,
    };
  },

  contextToAppId: ({ securityContext }) => {
    const connectionId = securityContext?.connection || 'default';
    return `CUBE_APP_${connectionId}`;
  },

  contextToOrchestratorId: ({ securityContext }) => {
    const connectionId = securityContext?.connection || 'default';
    const dataset = securityContext?.dataset || 'default';
    return `CUBE_ORCH_${connectionId}_${dataset}`;
  },

  scheduledRefreshContexts: async () => {
    try {
      return await getCachedContexts();
    } catch (e) {
      console.error('Failed to fetch refresh contexts:', e.message);
      return [];
    }
  },
};
