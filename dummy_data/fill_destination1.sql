CREATE TABLE IF NOT EXISTS paid_performance (
  source varchar(250) NOT NULL,
  campaign varchar(250) NOT NULL,
  impressions INT NOT NULL,
  clicks INT NOT NULL
);

INSERT INTO paid_performance (source, campaign, impressions, clicks)
VALUES
    ('facebook', 'Destination 1 - campaign 1', 130, 16),
    ('facebook', 'Destination 1 - campaign 2', 10, 8),
    ('facebook', 'Destination 1 - campaign 3', 340, 100),
    ('linkedin', 'Destination 1 - other campaign 1', 770, 70),
    ('linkedin', 'Destination 1 - other campaign 2', 1080, 320),
    ('google_ads', 'Destination 1 - google ads campaign 1', 6750, 526),
    ('google_ads', 'Destination 1 - google ads campaign 2', 8654, 352),
    ('google_ads', 'Destination 1 - google ads campaign 3', 343, 74),
    ('google_ads', 'Destination 1 - google ads campaign 4', 577, 73);
