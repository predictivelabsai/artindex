CREATE SCHEMA IF NOT EXISTS artindex;

CREATE TABLE IF NOT EXISTS artindex.auction_lots (
    id SERIAL PRIMARY KEY,
    auction_date BIGINT NOT NULL,
    author VARCHAR(255) NOT NULL,
    start_price BIGINT NOT NULL,
    end_price BIGINT NOT NULL,
    year BIGINT,
    decade BIGINT,
    tech VARCHAR(255),
    category VARCHAR(100),
    dimension DOUBLE PRECISION,
    auction_provider VARCHAR(100) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_auction_lots_provider ON artindex.auction_lots(auction_provider);
CREATE INDEX IF NOT EXISTS idx_auction_lots_author ON artindex.auction_lots(author);
CREATE INDEX IF NOT EXISTS idx_auction_lots_date ON artindex.auction_lots(auction_date);
