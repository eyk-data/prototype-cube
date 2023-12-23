CREATE TABLE IF NOT EXISTS paid_performance (
  source varchar(250) NOT NULL,
  campaign varchar(250) NOT NULL,
  impressions INT NOT NULL,
  clicks INT NOT NULL
);

INSERT INTO paid_performance (source, campaign, impressions, clicks)
VALUES
    ('facebook', 'Destination 2 - campaign 1', 5670, 53),
    ('facebook', 'Destination 2 - campaign 2', 7246, 62),
    ('facebook', 'Destination 2 - campaign 3', 1002, 770),
    ('linkedin', 'Destination 2 - other campaign 1', 41450, 210),
    ('linkedin', 'Destination 2 - other campaign 2', 6250, 114),
    ('google_ads', 'Destination 2 - google ads campaign 1', 14140, 537),
    ('google_ads', 'Destination 2 - google ads campaign 2', 9679, 79),
    ('google_ads', 'Destination 2 - google ads campaign 3', 9064, 135),
    ('google_ads', 'Destination 2 - google ads campaign 4', 46733, 477);
