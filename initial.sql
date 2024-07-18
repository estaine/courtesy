-- Create the 'club' table with the additional 'key' column
CREATE TABLE club (
                      id SERIAL PRIMARY KEY,
                      name VARCHAR(255) NOT NULL,
                      address VARCHAR(255),
                      key VARCHAR(50) NOT NULL
);

-- Create the 'court' table with the additional 'internal_id' column
CREATE TABLE court (
                       id SERIAL PRIMARY KEY,
                       club_id INTEGER REFERENCES club(id) ON DELETE CASCADE,
                       surface VARCHAR(50),
                       open BOOLEAN,
                       number INTEGER,
                       internal_id INTEGER
);

-- Create the 'booking' table
CREATE TABLE booking (
                         id SERIAL PRIMARY KEY,
                         actual BOOLEAN,
                         booked BOOLEAN,
                         data JSON
);
