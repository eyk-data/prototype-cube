import cubejs from '@cubejs-client/core';
import { QueryRenderer } from '@cubejs-client/react';
import { Spin } from 'antd';
import 'antd/dist/reset.css';
import React, { useState } from 'react';
import * as d3 from 'd3';
import { Row, Col, Statistic, Table } from 'antd';
import { useDeepCompareMemo } from 'use-deep-compare';

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
  const [destinations, setDestinations] = useState();
  const [selectedDestination, setSelectedDestination] = useState('');
  const [token, setToken] = useState('');

  const handleClick = () => {
    const xhr = new XMLHttpRequest();
    xhr.open('GET', 'http://localhost:8000/destinations/');
    xhr.onload = function () {
      if (xhr.status === 200) {
        setDestinations(JSON.parse(xhr.responseText));
      }
    };
    xhr.send();
  }

  const handleChangeSelect = (e) => {
    const id = e.target.value;
    setSelectedDestination(id)

    // Retrieve token
    const xhr = new XMLHttpRequest();
    xhr.open('GET', 'http://localhost:8000/destinations/' + id + '/token');
    xhr.onload = function () {
      if (xhr.status === 200) {
        setToken(JSON.parse(xhr.responseText));
      }
    };
    xhr.send();
  }

  const cubejsApi = cubejs(
    token,
    { apiUrl: 'http://localhost:4000/cubejs-api/v1' }
  );

  const ChartRenderer = () => {
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

  return (
    <div>
      {/* <div style={{ height: 30 }}> </div> */}
      <div style={{ height: 100, padding: 20}}>
        {destinations ?
          <div>
            <h2>Destinations loaded 🚀</h2>
            <t>Select destination: </t>
            <select name="Select destination" onChange={handleChangeSelect}>
              <option>-</option>
              {
                destinations.map(function (d) {
                  return (<option value={d['id']}>{d['hostname']}</option>);
                })
              }
            </select>
          </div>
          : <button onClick={handleClick}>List destinations from API</button>}
      </div>
      <ChartRenderer />
    </div>
  );
}

export default function MyApp() {
  return (
    <div style={{ width: 1000, margin: 'auto', padding: 50 }}>
      <h1>Cube multi-tenancy prototype</h1>
      <MyMultiTenantDataComponent />
    </div>
  );
}
