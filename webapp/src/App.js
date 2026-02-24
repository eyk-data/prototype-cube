import cubejs from "@cubejs-client/core";
import { QueryRenderer } from "@cubejs-client/react";
import { Spin } from "antd";
import "antd/dist/reset.css";
import React, { useState, useEffect, useMemo, useCallback } from "react";
import { Table } from "antd";
import { useDeepCompareMemo } from "use-deep-compare";
import Highlight from "react-highlight";

const formatTableData = (columns, data) => {
  function flatten(columns = []) {
    return columns.reduce((memo, column) => {
      if (column.children) {
        return [...memo, ...flatten(column.children)];
      }

      return [...memo, column];
    }, []);
  }

  const typeByIndex = flatten(columns).reduce((memo, column) => {
    return { ...memo, [column.dataIndex]: column };
  }, {});

  function formatValue(value, { type, format } = {}) {
    if (value == undefined) {
      return value;
    }

    if (type === "boolean") {
      if (typeof value === "boolean") {
        return value.toString();
      } else if (typeof value === "number") {
        return Boolean(value).toString();
      }

      return value;
    }

    if (type === "number" && format === "percent") {
      return [parseFloat(value).toFixed(2), "%"].join("");
    }

    return value.toString();
  }

  function format(row) {
    return Object.fromEntries(
      Object.entries(row).map(([dataIndex, value]) => {
        return [dataIndex, formatValue(value, typeByIndex[dataIndex])];
      })
    );
  }

  return data.map(format);
};

const TableRenderer = ({ resultSet, pivotConfig }) => {
  const [tableColumns, dataSource] = useDeepCompareMemo(() => {
    const columns = resultSet.tableColumns(pivotConfig);
    return [
      columns,
      formatTableData(columns, resultSet.tablePivot(pivotConfig)),
    ];
  }, [resultSet, pivotConfig]);
  return (
    <Table pagination={false} columns={tableColumns} dataSource={dataSource} />
  );
};

function ChartWithLogging({
  resultSet,
  error,
  pivotConfig,
  setLastDataLog,
  setLastErrorLog,
  children,
}) {
  useEffect(() => {
    if (error) {
      setLastErrorLog?.({
        message: error?.message,
        stack: error?.stack,
        name: error?.name,
      });
      setLastDataLog?.(null);
    } else if (resultSet && pivotConfig) {
      try {
        const tableData = resultSet.tablePivot(pivotConfig);
        const columns = resultSet.tableColumns(pivotConfig);
        const log = {
          rowCount: tableData?.length,
          columnCount: columns?.length,
          sampleRow: tableData?.[0],
          columnKeys: columns?.map((c) => c.key),
        };
        setLastDataLog?.(log);
        setLastErrorLog?.(null);
      } catch (_) {}
    }
  }, [resultSet, error]);
  return children;
}

const renderChart = (
  { resultSet, error, pivotConfig },
  setLastDataLog,
  setLastErrorLog
) => {
  if (error) {
    const errPayload = {
      message: error?.message,
      stack: error?.stack,
      name: error?.name,
    };
    console.error("[Cube] Query error", error);
    return (
      <ChartWithLogging
        resultSet={null}
        error={error}
        setLastDataLog={setLastDataLog}
        setLastErrorLog={setLastErrorLog}
      >
        <div>
          <div>{error.toString()}</div>
          <details style={{ marginTop: 8, fontSize: 12 }}>
            <summary>Error details (console has full object)</summary>
            <pre style={{ whiteSpace: "pre-wrap", wordBreak: "break-all" }}>
              {JSON.stringify(errPayload, null, 2)}
            </pre>
          </details>
        </div>
      </ChartWithLogging>
    );
  }

  if (!resultSet) {
    return <Spin />;
  }

  try {
    const tableData = resultSet.tablePivot(pivotConfig);
    const columns = resultSet.tableColumns(pivotConfig);
    console.log("[Cube] Data received", {
      rowCount: tableData?.length,
      columnCount: columns?.length,
    });
    return (
      <ChartWithLogging
        resultSet={resultSet}
        error={null}
        pivotConfig={pivotConfig}
        setLastDataLog={setLastDataLog}
        setLastErrorLog={setLastErrorLog}
      >
        <TableRenderer resultSet={resultSet} pivotConfig={pivotConfig} />
      </ChartWithLogging>
    );
  } catch (e) {
    console.error("[Cube] Render error", e);
    return (
      <ChartWithLogging
        resultSet={null}
        error={e}
        setLastDataLog={setLastDataLog}
        setLastErrorLog={setLastErrorLog}
      >
        <div>
          <div style={{ color: "red" }}>Render error: {e?.message}</div>
          <details style={{ marginTop: 8, fontSize: 12 }}>
            <summary>Details</summary>
            <pre style={{ whiteSpace: "pre-wrap" }}>{e?.stack}</pre>
          </details>
        </div>
      </ChartWithLogging>
    );
  }
};

const SERVER_URL = process.env.REACT_APP_SERVER_URL || "http://localhost:8000";
const CUBE_API_URL =
  process.env.REACT_APP_CUBE_API_URL || "http://localhost:4000/cubejs-api/v1";
const USE_SELF_HOSTED_CUBE =
  process.env.REACT_APP_USE_SELF_HOSTED_CUBE === "true";

const PAID_PERFORMANCE_QUERY = {
  measures: ["paid_performance.impressions", "paid_performance.clicks"],
  dimensions: ["paid_performance.source", "paid_performance.campaign_name"],
  order: { "paid_performance.impressions": "desc" },
};
const PAID_PERFORMANCE_PIVOT = {
  x: ["paid_performance.source", "paid_performance.campaign_name"],
  y: ["measures"],
  fillMissingDates: true,
  joinDateRange: false,
};

const ECOMMERCE_ATTRIBUTION_QUERY = {
  measures: [
    "ecommerce_attribution.gross_sales",
    "ecommerce_attribution.spend",
  ],
  dimensions: [
    "ecommerce_attribution.model",
    "ecommerce_attribution.source",
    "ecommerce_attribution.campaign_name",
  ],
  order: { "ecommerce_attribution.gross_sales": "desc" },
};
const ECOMMERCE_ATTRIBUTION_PIVOT = {
  x: [
    "ecommerce_attribution.model",
    "ecommerce_attribution.source",
    "ecommerce_attribution.campaign_name",
  ],
  y: ["measures"],
  fillMissingDates: true,
  joinDateRange: false,
};

function PaidPerformanceChart({ cubejsApi, setLastDataLog, setLastErrorLog }) {
  const render = useCallback(
    (props) =>
      renderChart(
        { ...props, pivotConfig: PAID_PERFORMANCE_PIVOT },
        setLastDataLog,
        setLastErrorLog
      ),
    [setLastDataLog, setLastErrorLog]
  );
  if (!cubejsApi) return <Spin />;
  return (
    <QueryRenderer
      query={PAID_PERFORMANCE_QUERY}
      cubejsApi={cubejsApi}
      resetResultSetOnChange={false}
      render={render}
    />
  );
}

function EcommerceAttributionChart({
  cubejsApi,
  setLastDataLog,
  setLastErrorLog,
}) {
  const render = useCallback(
    (props) =>
      renderChart(
        { ...props, pivotConfig: ECOMMERCE_ATTRIBUTION_PIVOT },
        setLastDataLog,
        setLastErrorLog
      ),
    [setLastDataLog, setLastErrorLog]
  );
  if (!cubejsApi) return <Spin />;
  return (
    <QueryRenderer
      query={ECOMMERCE_ATTRIBUTION_QUERY}
      cubejsApi={cubejsApi}
      resetResultSetOnChange={false}
      render={render}
    />
  );
}

const DebugData = ({ label, data }) => {
  const [open, setOpen] = useState(false);
  if (data === undefined) return null;
  return (
    <details style={{ marginTop: 8, fontSize: 12, fontFamily: "monospace" }}>
      <summary onClick={() => setOpen(!open)}>{label}</summary>
      <pre
        style={{
          whiteSpace: "pre-wrap",
          wordBreak: "break-all",
          maxHeight: 200,
          overflow: "auto",
        }}
      >
        {typeof data === "string" ? data : JSON.stringify(data, null, 2)}
      </pre>
    </details>
  );
};

function MyMultiTenantDataComponent() {
  const [tenants, setTenants] = useState();
  const [selectedTenant, setSelectedTenant] = useState();
  const [selectedDestination, setSelectedDestination] = useState();
  const [token, setToken] = useState();
  const [cubeTokenError, setCubeTokenError] = useState(null);
  const [lastDataLog, setLastDataLog] = useState(null);
  const [lastErrorLog, setLastErrorLog] = useState(null);

  useEffect(() => {
    if (!USE_SELF_HOSTED_CUBE) return;
    const req = new XMLHttpRequest();
    req.open("GET", `${SERVER_URL}/cube-token`);
    req.onload = function () {
      if (req.status === 200) {
        const raw = req.responseText;
        console.log("[Cube] Token received", {
          length: raw?.length,
          type: typeof raw,
          prefix: raw?.slice(0, 30),
        });
        setToken(raw);
      } else {
        setCubeTokenError(req.statusText || "Failed to get Cube token");
      }
    };
    req.onerror = () => setCubeTokenError("Network error");
    req.send();
  }, []);

  useEffect(() => {
    if (USE_SELF_HOSTED_CUBE || selectedTenant == null) return;

    const token_request = new XMLHttpRequest();
    token_request.open(
      "GET",
      `${SERVER_URL}/tenants/${selectedTenant.id}/token`
    );
    token_request.onload = function () {
      if (token_request.status === 200) {
        setToken(JSON.parse(token_request.responseText));
      }
    };
    token_request.send();

    const destination_request = new XMLHttpRequest();
    destination_request.open(
      "GET",
      `${SERVER_URL}/destinations/${selectedTenant.destination_id}`
    );
    destination_request.onload = function () {
      if (destination_request.status === 200) {
        setSelectedDestination(JSON.parse(destination_request.responseText));
      }
    };
    destination_request.send();
  }, [selectedTenant]);

  const handleClick = () => {
    const request = new XMLHttpRequest();
    request.open("GET", `${SERVER_URL}/tenants/`);
    request.onload = function () {
      if (request.status === 200) {
        setTenants(JSON.parse(request.responseText));
      }
    };
    request.send();
  };

  const handleChangeSelect = (e) => {
    const id = e.target.value;
    setSelectedTenant(tenants.find((tenant) => tenant.id === Number(id)));
  };

  const cubejsApi = useMemo(
    () => (token ? cubejs(token, { apiUrl: CUBE_API_URL }) : null),
    [token]
  );

  const showCubeData = USE_SELF_HOSTED_CUBE
    ? !!token
    : !!selectedTenant && !!token;

  return (
    <div>
      <hr style={{ borderTop: "3px solid #309676" }}></hr>
      <div style={{ height: 340, padding: 20 }}>
        {USE_SELF_HOSTED_CUBE ? (
          <>
            <h2>Self-hosted Cube (BigQuery)</h2>
            {cubeTokenError && (
              <p style={{ color: "red" }}>Error: {cubeTokenError}</p>
            )}
            {token && (
              <p>
                Cube JWT loaded ✅ — dataset from server (token length:{" "}
                {token.length})
              </p>
            )}
            {lastDataLog && (
              <DebugData
                label="📋 Last data from Cube (click to expand)"
                data={lastDataLog}
              />
            )}
            {lastErrorLog && (
              <DebugData
                label="❌ Last error (click to expand)"
                data={lastErrorLog}
              />
            )}
          </>
        ) : tenants ? (
          <div>
            <h2>Tenants loaded ✅</h2>
            <p>
              Select tenant:
              <select
                name="Select tenant"
                onChange={handleChangeSelect}
                style={{ margin: 10 }}
              >
                <option value="">-</option>
                {tenants.map(function (t) {
                  return (
                    <option key={t["id"]} value={t["id"]}>
                      {t["name"]}
                    </option>
                  );
                })}
              </select>
            </p>
            {selectedTenant && (
              <div
                style={{
                  textAlign: "left",
                  display: "flex",
                  flexDirection: "row",
                  justifyContent: "space-around",
                }}
              >
                <div>
                  <b>Tenant config</b>
                  <Highlight className="json">
                    {JSON.stringify(selectedTenant, null, 2)}
                  </Highlight>
                </div>
                <div>
                  <b>Destination config</b>
                  <Highlight className="json">
                    {JSON.stringify(selectedDestination, null, 2)}
                  </Highlight>
                </div>
              </div>
            )}
          </div>
        ) : (
          <button onClick={handleClick}>List tenants from API</button>
        )}
      </div>
      <h2>💎 Data retrieved from Cube 💎</h2>
      <hr style={{ borderTop: "3px solid #309676" }}></hr>
      <b>📢 Paid Performance 📢</b>
      {showCubeData ? (
        <PaidPerformanceChart
          cubejsApi={cubejsApi}
          setLastDataLog={setLastDataLog}
          setLastErrorLog={setLastErrorLog}
        />
      ) : (
        <p>
          {USE_SELF_HOSTED_CUBE
            ? cubeTokenError
              ? "Check server and CUBEJS_BQ_DATASET"
              : "Loading Cube token…"
            : "no tenant selected"}
        </p>
      )}
      <hr style={{ borderTop: "2px solid #309676" }}></hr>
      <b>🔮 Ecommerce Attribution 🔮</b>
      {showCubeData ? (
        <EcommerceAttributionChart
          cubejsApi={cubejsApi}
          setLastDataLog={setLastDataLog}
          setLastErrorLog={setLastErrorLog}
        />
      ) : (
        <p>no tenant selected</p>
      )}
      <hr style={{ borderTop: "2px solid #309676" }}></hr>
    </div>
  );
}

export default function MyApp() {
  return (
    <div
      style={{ width: 1000, margin: "auto", padding: 50, textAlign: "center" }}
    >
      <h1>
        <b>Eyk x Cube x Embeddable</b>
      </h1>
      <h3>multi-tenancy prototype</h3>
      <MyMultiTenantDataComponent />
    </div>
  );
}
