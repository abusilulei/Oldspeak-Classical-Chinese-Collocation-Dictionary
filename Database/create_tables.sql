CREATE DATABASE oldspeak;
\c oldspeak

-- Books Table
CREATE TABLE books (
    book_id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    category VARCHAR(20),
    period VARCHAR(20),
    style VARCHAR(20),
    CONSTRAINT unq_books_name UNIQUE (name)
);

-- Sentences Table
CREATE TABLE sentences (
    sentence_id SERIAL PRIMARY KEY,
    book_id INT NOT NULL,
    content TEXT NOT NULL,
    CONSTRAINT fk_sentences_book FOREIGN KEY (book_id) 
        REFERENCES books(book_id) ON DELETE CASCADE
);
-- Create a unique index on a prefix of content for uniqueness per book.
-- This is a pragmatic choice for performance; if true uniqueness is needed for very long sentences,
-- consider storing a hash of the content.
CREATE UNIQUE INDEX idx_sentences_book_content ON sentences (book_id, left(content, 255)); -- Increased prefix length

-- Tokens Table
CREATE TABLE tokens (
    token_id SERIAL PRIMARY KEY,
    sentence_id INT NOT NULL,
    position INT NOT NULL,      -- Starting from 0 (When inserting, you should minus 1)
    token_text VARCHAR(100) NOT NULL,
    pos_tag VARCHAR(50),
    CONSTRAINT fk_tokens_sentence FOREIGN KEY (sentence_id) 
        REFERENCES sentences(sentence_id) ON DELETE CASCADE,
    CONSTRAINT unq_tokens_sentence_position UNIQUE (sentence_id, position)
);

-- Dependencies Table
CREATE TABLE dependencies (
    dependency_id SERIAL PRIMARY KEY,
    head_token_id INT NOT NULL,
    dependent_token_id INT NOT NULL, -- if ROOT, point to itself
    dependency_type VARCHAR(50) NOT NULL,
    CONSTRAINT fk_dependencies_head FOREIGN KEY (head_token_id) 
        REFERENCES tokens(token_id) ON DELETE CASCADE,
    CONSTRAINT fk_dependencies_dependent FOREIGN KEY (dependent_token_id) 
        REFERENCES tokens(token_id) ON DELETE CASCADE,
    CONSTRAINT unq_dependencies_dependent UNIQUE (dependent_token_id) -- Each token has only one head
);

-- Index for filtering by book metadata
CREATE INDEX idx_books_category ON books(category);
CREATE INDEX idx_books_period ON books(period);
CREATE INDEX idx_books_style ON books(style);

-- Combined metadata index for multi-criteria filtering
CREATE INDEX idx_books_metadata ON books(category, period, style);

-- Full-text search capabilities for content
CREATE INDEX idx_sentences_book_id ON sentences(book_id);
CREATE INDEX idx_sentences_length ON sentences(length(content));

-- For PostgreSQL, use GIN index for full text search
-- CREATE INDEX idx_sentences_content_gin ON sentences USING gin(to_tsvector('chinese', content));

-- Word and part-of-speech filtering
CREATE INDEX idx_tokens_text ON tokens(token_text);
CREATE INDEX idx_tokens_pos ON tokens(pos_tag);

-- Position-based lookup
CREATE INDEX idx_tokens_sentence_position ON tokens(sentence_id, position);

-- Combined POS + text index for specific token type searches
CREATE INDEX idx_tokens_pos_text ON tokens(pos_tag, token_text);

-- Relationship type filtering
CREATE INDEX idx_dependencies_type ON dependencies(dependency_type);

-- Find all tokens governed by a specific head
CREATE INDEX idx_dependencies_head ON dependencies(head_token_id);

-- Find the head of a specific token
CREATE INDEX idx_dependencies_dependent ON dependencies(dependent_token_id);

-- Find specific dependency types from specific heads
CREATE INDEX idx_dependencies_head_type ON dependencies(head_token_id, dependency_type);