import cubejs from '@cubejs-client/core';
import { QueryRenderer } from '@cubejs-client/react';
import { Spin } from 'antd';
import 'antd/dist/reset.css';
import React, { useState, useEffect } from 'react';
import { Table } from 'antd';
import { useDeepCompareMemo } from 'use-deep-compare';
import Highlight from 'react-highlight';


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

    if (type === 'boolean') {
      if (typeof value === 'boolean') {
        return value.toString();
      } else if (typeof value === 'number') {
        return Boolean(value).toString();
      }

      return value;
    }

    if (type === 'number' && format === 'percent') {
      return [parseFloat(value).toFixed(2), '%'].join('');
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

const renderChart = ({ resultSet, error, pivotConfig, onDrilldownRequested }) => {
  if (error) {
    return <div>{error.toString()}</div>;
  }

  if (!resultSet) {
    return <Spin />;
  }

  return <TableRenderer resultSet={resultSet} pivotConfig={pivotConfig} />;

};

function MyMultiTenantDataComponent() {
  const [tenants, setTenants] = useState();
  const [selectedTenant, setSelectedTenant] = useState();
  const [selectedDestination, setSelectedDestination] = useState();
  const [token, setToken] = useState();

  useEffect(() => {

    if (selectedTenant == null) {
      return
    }

    // Retrieve token
    const token_request = new XMLHttpRequest();
    token_request.open('GET', 'http://localhost:8000/tenants/' + selectedTenant.id + '/token');
    token_request.onload = function () {
      if (token_request.status === 200) {
        setToken(JSON.parse(token_request.responseText));
      }
    };
    token_request.send();

    // Retrieve destination
    const destination_request = new XMLHttpRequest();
    destination_request.open('GET', 'http://localhost:8000/destinations/' + selectedTenant.destination_id);
    destination_request.onload = function () {
      if (destination_request.status === 200) {
        setSelectedDestination(JSON.parse(destination_request.responseText));
      }
    };
    destination_request.send();
  }, [selectedTenant]);

  const handleClick = () => {
    const request = new XMLHttpRequest();
    request.open('GET', 'http://localhost:8000/tenants/');
    request.onload = function () {
      if (request.status === 200) {
        setTenants(JSON.parse(request.responseText));
      }
    };
    request.send();
  }

  const handleChangeSelect = (e) => {
    const id = e.target.value;
    setSelectedTenant(tenants.find(tenant => tenant.id === Number(id)));
  }

  const cubejsApi = cubejs(
    token,
    { apiUrl: 'http://localhost:4000/cubejs-api/v1' }
  );

  const PaidPerformanceRenderer = () => {
    return (
      <QueryRenderer
        query={{
          "measures": [
            "paid_performance.total_impressions",
            "paid_performance.total_clicks"
          ],
          "dimensions": [
            "paid_performance.source",
            "paid_performance.campaign"
          ],
          "order": {
            "paid_performance.total_impressions": "desc"
          }
        }}
        cubejsApi={cubejsApi}
        resetResultSetOnChange={false}
        render={(props) => renderChart({
          ...props,
          chartType: 'table',
          pivotConfig: {
            "x": [
              "paid_performance.source",
              "paid_performance.campaign"
            ],
            "y": [
              "measures"
            ],
            "fillMissingDates": true,
            "joinDateRange": false
          }
        })}
      />
    );
  };

  const EcommerceAttributionRenderer = () => {
    return (
      <QueryRenderer
        query={{
          "measures": [
            "ecommerce_attribution_models.total_revenue"
          ],
          "dimensions": [
            "ecommerce_attribution_models.model",
            "ecommerce_attribution_models.source",
            "ecommerce_attribution_models.medium",
            "ecommerce_attribution_models.campaign"
          ],
          "order": {
            "ecommerce_attribution_models.total_revenue": "desc"
          }
        }}
        cubejsApi={cubejsApi}
        resetResultSetOnChange={false}
        render={(props) => renderChart({
          ...props,
          chartType: 'table',
          pivotConfig: {
            "x": [
              "ecommerce_attribution_models.model",
              "ecommerce_attribution_models.source",
              "ecommerce_attribution_models.medium",
              "ecommerce_attribution_models.campaign"
            ],
            "y": [
              "measures"
            ],
            "fillMissingDates": true,
            "joinDateRange": false
          }
        })}
      />
    );
  };


  return (
    <div>
      <hr style={{ borderTop: "3px solid #309676" }}></hr>
      <div style={{ height: 340, padding: 20 }}>
        {tenants ?
          <div>
            <h2>Tenants loaded ✅</h2>
            <p>
              Select tenant:
              <select name="Select tenant" onChange={handleChangeSelect} style={{ margin: 10}}>
                <option value=''>-</option>
                {
                  tenants.map(function (t) {
                    return (<option key={t['id']} value={t['id']}>{t['name']}</option>);
                  })
                }
              </select></p>
            {selectedTenant ?
              <div style={{ textAlign: 'left', display: 'flex', flexDirection: 'row', justifyContent: 'space-around' }}>
                <div>
                  <b>Tenant config</b>
                  <Highlight className='json'>
                    {JSON.stringify(selectedTenant, null, 2)}
                  </Highlight>
                </div>
                <div>
                  <b>Destination config</b>
                  <Highlight className='json'>
                    {JSON.stringify(selectedDestination, null, 2)}
                  </Highlight>
                </div>
              </div> :
              <div></div>
            }
          </div> :
          <button onClick={handleClick}>List tenants from API</button>}
      </div>
      <h2>💎 Data retrieved from Cube 💎</h2>
      <hr style={{ borderTop: "3px solid #309676" }}></hr>
      <b>📢 Paid Performance 📢</b>
      {selectedTenant ?
        <PaidPerformanceRenderer /> :
        <p>no tenant selected</p>
      }
      <hr style={{ borderTop: "2px solid #309676" }}></hr>
      <b>🔮 Ecommerce Attribution 🔮</b>
      {selectedTenant ?
        <EcommerceAttributionRenderer /> :
        <p>no tenant selected</p>
      }
      <hr style={{ borderTop: "2px solid #309676" }}></hr>
    </div>
  );
}

export default function MyApp() {
  return (
    <div style={{ width: 1000, margin: 'auto', padding: 50, textAlign: 'center' }}>
      <h1><b>Eyk x Cube x Embeddable</b></h1>
      <h3>multi-tenancy prototype</h3>
      <MyMultiTenantDataComponent />
    </div>
  );
}
