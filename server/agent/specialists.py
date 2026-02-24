from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SpecialistConfig:
    domain: str
    system_instructions: str
    cube_meta_context: str


MARKETING_SPECIALIST = SpecialistConfig(
    domain="marketing",
    system_instructions=(
        "You are a Marketing Analytics specialist. You help users understand their "
        "advertising performance, attribution, email campaigns, and marketing ROI. "
        "Always use the cube_builder_tool to construct a valid CubeJS query before "
        "answering. Use exact cube member names from the metadata below."
    ),
    cube_meta_context="""\
## Available Cubes & Members

### fact_daily_ads (Daily Ads)
Measures: fact_daily_ads.impressions (sum), fact_daily_ads.clicks (sum), fact_daily_ads.cost (sum), fact_daily_ads.revenue (sum), fact_daily_ads.orders (sum), fact_daily_ads.click_through_rate (calculated), fact_daily_ads.cost_per_click (calculated), fact_daily_ads.cost_per_mille (calculated)
Dimensions: fact_daily_ads.date (time), fact_daily_ads.source (string), fact_daily_ads.campaign_id (string), fact_daily_ads.campaign_name (string), fact_daily_ads.campaign_objective_type (string), fact_daily_ads.ad_group_id (string), fact_daily_ads.ad_group_name (string), fact_daily_ads.ad_id (string), fact_daily_ads.ad_name (string), fact_daily_ads.account_name (string), fact_daily_ads.currency (string)

### fact_attributions (Attributed Sales Items)
Measures: fact_attributions.channel_impressions (sum), fact_attributions.channel_clicks (sum), fact_attributions.channel_cost (sum), fact_attributions.channel_revenue (sum), fact_attributions.channel_orders (sum), fact_attributions.gross_sales (sum), fact_attributions.net_sales (sum), fact_attributions.total_sales (sum), fact_attributions.gross_profit (sum), fact_attributions.contribution_profit (sum), fact_attributions.orders (sum), fact_attributions.first_time_customer_orders (sum), fact_attributions.average_order_value (calculated), fact_attributions.gross_margin (calculated), fact_attributions.return_rate (calculated), fact_attributions.discount_rate (calculated), fact_attributions.eyk_return_on_ad_spend (calculated), fact_attributions.channel_return_on_ad_spend (calculated), fact_attributions.cost_per_acquisition (calculated)
Dimensions: fact_attributions.combined_source (string – Channel), fact_attributions.combined_campaign (string), fact_attributions.combined_ad_group (string), fact_attributions.combined_ad (string), fact_attributions.combined_timestamp (time), fact_attributions.attribution_model (string), fact_attributions.channel_source (string), fact_attributions.store (string), fact_attributions.sales_channel (string), fact_attributions.billing_country_code (string), fact_attributions.shipping_country_code (string), fact_attributions.first_time_customer (string)
Joins: dim_product_variants, dim_customers, dim_attribution_models, fact_daily_ads

### email_performance (Email Performance)
Measures: email_performance.received (sum), email_performance.opened (sum), email_performance.unique_opened (sum), email_performance.clicked (sum), email_performance.unique_clicked (sum), email_performance.bounced (sum), email_performance.unsubscribed (sum), email_performance.attributed_revenue (sum), email_performance.attributed_orders (sum), email_performance.open_rate (calculated), email_performance.click_through_rate (calculated), email_performance.conversion_rate (calculated)
Dimensions: email_performance.source (string), email_performance.date (time), email_performance.flow (string), email_performance.campaign (string)

### dim_attribution_models
Dimensions: dim_attribution_models.model (string), dim_attribution_models.display_name (string)

## Query Format
- Time dimensions use: {"dimension": "cube.field", "granularity": "day|week|month|quarter|year", "dateRange": "Last 30 days"}
- Filters use: {"member": "cube.field", "operator": "equals|notEquals|contains|gt|lt|gte|lte|set|notSet|inDateRange", "values": ["..."]}
- Order uses: {"cube.field": "asc|desc"}
- Always prefix member names with the cube name (e.g. fact_daily_ads.impressions, NOT just impressions)
""",
)


SALES_SPECIALIST = SpecialistConfig(
    domain="sales",
    system_instructions=(
        "You are a Sales Analytics specialist. You help users understand their "
        "sales performance, product metrics, customer data, and profitability. "
        "Always use the cube_builder_tool to construct a valid CubeJS query before "
        "answering. Use exact cube member names from the metadata below."
    ),
    cube_meta_context="""\
## Available Cubes & Members

### fact_sales_items (Sales Items)
Measures: fact_sales_items.count_items (count), fact_sales_items.count_groups (count_distinct), fact_sales_items.customers (count_distinct), fact_sales_items.orders (count_distinct), fact_sales_items.first_time_customer_orders (count_distinct), fact_sales_items.returning_customer_orders (count_distinct), fact_sales_items.first_time_customers (count_distinct), fact_sales_items.returning_customers (count_distinct), fact_sales_items.net_quantity (sum), fact_sales_items.gross_sales (sum), fact_sales_items.discounts (sum), fact_sales_items.returns (sum), fact_sales_items.net_sales (sum), fact_sales_items.shipping (sum), fact_sales_items.taxes (sum), fact_sales_items.total_sales (sum), fact_sales_items.product_cost (sum), fact_sales_items.product_cost_combined (sum), fact_sales_items.gross_profit (sum), fact_sales_items.average_order_value (calculated), fact_sales_items.gross_margin (calculated), fact_sales_items.return_rate (calculated), fact_sales_items.discount_rate (calculated)
Dimensions: fact_sales_items.source (string), fact_sales_items.store (string), fact_sales_items.source_store (string), fact_sales_items.sales_channel (string), fact_sales_items.line_type (string), fact_sales_items.line_timestamp (time), fact_sales_items.line_status (string), fact_sales_items.group_type (string), fact_sales_items.group_status (string), fact_sales_items.group_timestamp (time), fact_sales_items.first_time_customer (string), fact_sales_items.first_subscription_group (string), fact_sales_items.billing_country_code (string), fact_sales_items.shipping_country_code (string)
Joins: dim_product_variants, dim_customers

### dim_product_variants (Product Variants)
Measures: dim_product_variants.count_products (count_distinct), dim_product_variants.count_variants (count_distinct)
Dimensions: dim_product_variants.source (string), dim_product_variants.store_name (string), dim_product_variants.variant_name (string), dim_product_variants.variant_type (string), dim_product_variants.product_name (string), dim_product_variants.product_type (string), dim_product_variants.combined_sku (string), dim_product_variants.combined_price (number), dim_product_variants.combined_cost (number), dim_product_variants.combined_name (string)

### dim_customers (Customers)
Dimensions: dim_customers.eyk_customer_id (string), dim_customers.first_name (string), dim_customers.last_name (string), dim_customers.email (string), dim_customers.created_at (string)

## Query Format
- Time dimensions use: {"dimension": "cube.field", "granularity": "day|week|month|quarter|year", "dateRange": "Last 30 days"}
- Filters use: {"member": "cube.field", "operator": "equals|notEquals|contains|gt|lt|gte|lte|set|notSet|inDateRange", "values": ["..."]}
- Order uses: {"cube.field": "asc|desc"}
- When querying sales with product details, use fact_sales_items measures with dim_product_variants dimensions (they are joined)
- Always prefix member names with the cube name (e.g. fact_sales_items.gross_sales, NOT just gross_sales)
""",
)


SPECIALISTS = {
    "marketing": MARKETING_SPECIALIST,
    "sales": SALES_SPECIALIST,
}
