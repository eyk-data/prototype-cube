CREATE TABLE IF NOT EXISTS paid_performance (
  source varchar(250) NOT NULL,
  campaign varchar(250) NOT NULL,
  impressions INT NOT NULL,
  clicks INT NOT NULL
);

INSERT INTO paid_performance (source, campaign, impressions, clicks)
VALUES
    ('facebook', 'Destination 2 - campaign 1', 5670, 53),
    ('linkedin', 'Destination 2 - other campaign 2', 6250, 114),
    ('google_ads', 'Destination 2 - google ads campaign 3', 14140, 537),
    ('google_ads', 'Destination 2 - google ads campaign 4', 46733, 477);

CREATE TABLE IF NOT EXISTS ecommerce_attribution_models (
  model varchar(250) NOT NULL,
  source varchar(250) NOT NULL,
  medium varchar(250) NOT NULL,
  campaign varchar(250) NOT NULL,
  revenue NUMERIC(10, 2) NOT NULL
);

INSERT INTO ecommerce_attribution_models (model, source, medium, campaign, revenue)
VALUES
    ('first_touch', 'google', 'cpc', 'Destination 2 campaign 1', 101.11),
    ('linear', 'google', 'organic', '', 5.19),
    ('last_touch', 'facebook', 'social', '', 408.93),
    ('first_touch', 'google', 'cpc', 'Destination 2 campaign 2', 123.00),
    ('time_decay', 'direct', '', '', 99.13);
