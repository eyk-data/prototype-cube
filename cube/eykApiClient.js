/**
 * EYK API Client
 * Handles authentication and API requests to the EYK backend
 */

class EykApiClient {
  constructor(baseUrl, username, password) {
    this.baseUrl = baseUrl;
    this.username = username;
    this.password = password;
    this.accessToken = null;
    this.tokenExpiry = null;
  }

  /**
   * Decode JWT token and extract payload
   * @param {string} token - JWT token
   * @returns {Object} Decoded payload
   * @private
   */
  decodeJWT(token) {
    try {
      const parts = token.split('.');
      if (parts.length !== 3) {
        throw new Error('Invalid JWT token format');
      }

      // Decode the payload (second part)
      const payload = parts[1];
      const decodedPayload = Buffer.from(payload, 'base64').toString('utf-8');
      return JSON.parse(decodedPayload);
    } catch (error) {
      console.error('Failed to decode JWT token:', error);
      throw new Error(`JWT decode error: ${error.message}`);
    }
  }

  /**
   * Login and obtain JWT access token
   * @returns {Promise<string>} Access token
   */
  async login() {
    try {
      const url = `${this.baseUrl}/auth/jwt/create/`;

      console.log('Authenticating with EYK API...');

      const response = await fetch(url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          email: this.username,
          password: this.password,
        }),
      });

      const data = await response.json();

      if (!response.ok) {
        console.error('Authentication failed. Response:', JSON.stringify(data, null, 2));
        throw new Error(`Authentication failed: ${response.status} ${response.statusText}`);
      }

      if (!data.access) {
        throw new Error('No access token received from authentication');
      }

      this.accessToken = data.access;

      // Decode token to get expiry from exp claim
      const payload = this.decodeJWT(data.access);

      if (payload.exp) {
        // JWT exp claim is in seconds since epoch, convert to milliseconds
        this.tokenExpiry = payload.exp * 1000;
        const expiryDate = new Date(this.tokenExpiry);
        console.log(`Token will expire at: ${expiryDate.toISOString()}`);
      } else {
        // Fallback to 15 minutes if no exp claim
        console.warn('No exp claim found in JWT, using 15 minute default expiry');
        this.tokenExpiry = Date.now() + (15 * 60 * 1000);
      }

      console.log('Successfully authenticated with EYK API');
      return this.accessToken;
    } catch (error) {
      console.error('Login failed:', error);
      throw new Error(`Failed to authenticate: ${error.message}`);
    }
  }

  /**
   * Ensure we have a valid access token
   * Refreshes the token 30 seconds before expiry to prevent edge cases
   * @private
   */
  async ensureAuthenticated() {
    // Add a 30 second buffer before actual expiry to prevent edge cases
    const bufferMs = 30 * 1000;
    if (!this.accessToken || (this.tokenExpiry && Date.now() >= (this.tokenExpiry - bufferMs))) {
      await this.login();
    }
  }

  /**
   * Get scheduler contexts from the API
   * @returns {Promise<Array>} Array of scheduler contexts
   */
  async getSchedulerContexts() {
    try {
      await this.ensureAuthenticated();

      const url = `${this.baseUrl}/api/cube/config/refresh-contexts`;

      console.log('Fetching scheduler contexts...');

      const response = await fetch(url, {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${this.accessToken}`,
        },
      });

      if (!response.ok) {
        throw new Error(`Failed to fetch scheduler contexts: ${response.status} ${response.statusText}`);
      }

      const data = await response.json();
      console.log(`Successfully fetched ${data.length || 0} scheduler context(s)`);

      return data;
    } catch (error) {
      console.error('Failed to fetch scheduler contexts:', error);
      throw new Error(`Failed to get scheduler contexts: ${error.message}`);
    }
  }

  /**
   * Get service account configuration for a specific cube connection
   * @param {string} connectionId - The cube connection ID
   * @returns {Promise<Object>} Service account configuration with projectId, jsonKey, and location
   */
  async getServiceAccount(connectionId) {
    if (!connectionId) {
      throw new Error('Connection ID is required');
    }

    try {
      await this.ensureAuthenticated();

      const url = `${this.baseUrl}/api/cube/config/${connectionId}/service-account`;

      console.log(`Fetching service account config for connection: ${connectionId}`);

      const response = await fetch(url, {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${this.accessToken}`,
        },
      });

      if (!response.ok) {
        throw new Error(`Failed to fetch service account config: ${response.status} ${response.statusText}`);
      }

      const config = await response.json();

      if (!config || !config.project_id) {
        console.error('Invalid service account config:', JSON.stringify(config, null, 2));
        throw new Error(`Invalid configuration received for connection: ${connectionId}`);
      }

      console.log(`Successfully fetched service account config for connection: ${connectionId}`);
      return config;
    } catch (error) {
      console.error(`Failed to fetch service account config for connection ${connectionId}:`, error);
      throw new Error(`Failed to get service account config: ${error.message}`);
    }
  }
}

module.exports = EykApiClient;
