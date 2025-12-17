from fastapi import FastAPI, HTTPException, Query
import asyncpg
import os
import asyncio
import re
import logging
from typing import List, Optional, Dict, Any

# CORS issue
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust this as necessary
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize connection pool
@app.on_event("startup")
async def startup():
    database_url = os.getenv("DATABASE_URL")
    print(f"Using database URL: {database_url}")  # Debug print to verify
    
    if not database_url:
        raise ValueError("DATABASE_URL environment variable not set")
    
    try:
        app.state.db_pool = await asyncpg.create_pool(
            dsn=database_url,
            # Remove or comment out any host/port overrides here
            # host="localhost",  # If you have this, remove it!
            # ssl=True  # Keep this if you need SSL
        )
    except Exception as e:
        logging.error(f"Failed to create database connection pool: {e}")
        raise

@app.on_event("shutdown")
async def shutdown():
    """Close database connection pool on shutdown."""
    if hasattr(app.state, 'db_pool') and app.state.db_pool:
        await app.state.db_pool.close()
        logger.info("Database connection pool closed.")

@app.get("/search")
async def search_dependencies(
    # Collocation search parameters
    head_text: Optional[str] = Query(None, description="Text of the **HEAD** token. Supports partial match with LIKE."),
    head_pos: Optional[List[str]] = Query(None, description="List of POS tags for the **HEAD** token. Uses OR operator for multiple tags."),
    dpdt_text: Optional[str] = Query(None, description="Text of the **DEPENDENT** token. Supports partial match with LIKE."),
    dpdt_pos: Optional[List[str]] = Query(None, description="List of POS tags for the **DEPENDENT** token. Uses OR operator for multiple tags."),
    dep_type: Optional[List[str]] = Query(None, description="List of dependency types. Uses OR operator for multiple types."),
    freq_inf: int = Query(1, ge=1, description="Minimum frequency for a collocation."),
    freq_sup: Optional[int] = Query(None, ge=1, description="Maximum frequency for a collocation."),
    
    # Pagination parameters
    results_limit: int = Query(8, gt=0, description="Maximum number of results to return."),
    results_offset: int = Query(0, ge=0, description="Results offset for pagination."),
    examples_limit: int = Query(5, gt=0, description="Maximum number of example sentences to return per collocation."),
    examples_offset: int = Query(0, ge=0, description="Offset for example sentences in the results."),
    
    # Parameters for example filtering
    book_names: Optional[List[str]] = Query(None, description="Filter examples by specific book names."),
    book_categories: Optional[List[str]] = Query(None, description="Filter examples by book categories."),
    book_periods: Optional[List[str]] = Query(None, description="Filter examples by historical periods."),
    book_styles: Optional[List[str]] = Query(None, description="Filter examples by writing styles.")
) -> Dict[str, Any]:
    """
    Searches for collocations based on head and dependent token properties,
    dependency type, and frequency. Can also filter example sentences by book metadata.
    """
    # Parameter validation
    if not head_text and not dpdt_text:
        raise HTTPException(
            status_code=400,
            detail="At least one of 'head_text' or 'dpdt_text' must be provided."
        )

    try:
        async with app.state.db_pool.acquire() as connection:
            where_clauses = []
            params = []
            param_counter = 1

            # Update references to match materialized view column names
            if head_text:
                where_clauses.append(f"head_text LIKE ${param_counter}")
                params.append(f"%{head_text}%")
                param_counter += 1
            if dpdt_text:
                where_clauses.append(f"dependent_text LIKE ${param_counter}")
                params.append(f"%{dpdt_text}%")
                param_counter += 1

            # Update POS tag filters
            if head_pos:
                where_clauses.append(f"head_pos = ANY(${param_counter}::text[])")
                params.append(head_pos)
                param_counter += 1
            if dpdt_pos:
                where_clauses.append(f"dependent_pos = ANY(${param_counter}::text[])")
                params.append(dpdt_pos)
                param_counter += 1

            # Update dependency type filter
            if dep_type:
                where_clauses.append(f"dependency_type = ANY(${param_counter}::text[])")
                params.append(dep_type)
                param_counter += 1

            # --- Omitted General Restrictions (as they were commented out) ---
            # If you want to add them back, ensure column names are correct
            # excluded_pos_tags = ["PUNCT", "SYM", "PROPN"]
            # excluded_dep_types = ["root", "cl", ...]
            # where_clauses.append(f"dependent_pos NOT IN ({', '.join(f"'{tag}'" for tag in excluded_pos_tags)})")
            # where_clauses.append(f"head_pos NOT IN ({', '.join(f"'{tag}'" for tag in excluded_pos_tags)})")
            # if not dep_type:
            #     where_clauses.append(f"dependency_type NOT IN ({', '.join(f"'{typ}'" for typ in excluded_dep_types)})")

            final_where_sql = " AND ".join(where_clauses)
            
            # Track parameter positions for all variables
            freq_inf_pos = param_counter
            param_counter += 1
            
            freq_sup_pos = None
            if freq_sup is not None:
                freq_sup_pos = param_counter
                param_counter += 1
            
            # Parameter positions for example filtering
            book_names_pos = None
            if book_names:
                book_names_pos = param_counter
                param_counter += 1
                
            categories_pos = None
            if book_categories:
                categories_pos = param_counter
                param_counter += 1
                
            periods_pos = None
            if book_periods:
                periods_pos = param_counter
                param_counter += 1
                
            styles_pos = None
            if book_styles:
                styles_pos = param_counter
                param_counter += 1
            
            # Example pagination parameters positions
            examples_limit_pos = param_counter
            param_counter += 1
            
            examples_offset_pos = param_counter
            param_counter += 1
            
            # Results pagination parameters positions
            results_limit_pos = param_counter
            param_counter += 1
            
            results_offset_pos = param_counter
            param_counter += 1

            # Build the book filtering WHERE clause (reusable part)
            book_filter_conditions = []
            if book_names:
                book_filter_conditions.append(f"name = ANY(${book_names_pos}::text[])")
            if book_categories:
                book_filter_conditions.append(f"category = ANY(${categories_pos}::text[])")
            if book_periods:
                book_filter_conditions.append(f"period = ANY(${periods_pos}::text[])")
            if book_styles:
                book_filter_conditions.append(f"style = ANY(${styles_pos}::text[])")
            
            # This SQL snippet forms the INNER JOIN for book filtering
            # It will be injected into both example subqueries
            books_filter_inner_sql = ""
            if book_filter_conditions:
                books_filter_inner_sql = f"""
                INNER JOIN (
                    SELECT name FROM books
                    WHERE {' AND '.join(book_filter_conditions)}
                ) AS boo ON boo.name = e->>'book'
                """

            # Construct the example fetching subquery (for the 'examples' column in results)
            example_fetch_sql = f"""
                (SELECT jsonb_agg(e) FROM (
                    SELECT e FROM jsonb_array_elements(examples) AS e
                    {books_filter_inner_sql} -- Use the reusable filter
                    LIMIT ${examples_limit_pos} OFFSET ${examples_offset_pos}
                ) AS limited_examples)
            """

            # Construct the total matching examples count subquery (for 'example_count' column)
            total_matching_examples_count_sql = f"""
                (SELECT COUNT(*)
                FROM jsonb_array_elements(examples) AS e
                {books_filter_inner_sql} -- Use the reusable filter
                )
            """

            # Construct the main query string with dynamic example filtering and pagination
            query_template = f"""
                SELECT
                    dependent_text, dependent_pos, head_text, head_pos,
                    dependency_type,
                    {example_fetch_sql} AS examples,
                    mv_token_collocations.frequency, -- KEEP original frequency column
                    {total_matching_examples_count_sql} AS example_count, -- NEW column for total examples
                    COUNT(*) OVER() AS total_collocations_count -- Renamed for clarity
                FROM
                    mv_token_collocations
                WHERE
                    {final_where_sql}
                    AND mv_token_collocations.frequency >= ${freq_inf_pos}
                    {"AND mv_token_collocations.frequency <= $" + str(freq_sup_pos) if freq_sup is not None else ""}
                ORDER BY
                    example_count DESC
                LIMIT ${results_limit_pos} OFFSET ${results_offset_pos};
            """
            
            # Add all parameters in the correct order
            params.append(freq_inf)
            if freq_sup is not None:
                params.append(freq_sup)
                
            # Add book filter parameters (order matters based on param_counter)
            if book_names:
                params.append(book_names)
            if book_categories:
                params.append(book_categories)
            if book_periods:
                params.append(book_periods)
            if book_styles:
                params.append(book_styles)
                
            # Add pagination parameters
            params.append(examples_limit)
            params.append(examples_offset)
            params.append(results_limit)
            params.append(results_offset)

            logger.info(f"Executing query with params: {params}")
            logger.debug(f"Full query: {query_template}")

            # Fetch results
            result = await connection.fetch(query_template, *params)
            collocations = [dict(row) for row in result]

            # Extract `total_collocations_count` and remove it from each row
            total_collocations_count = collocations[0]["total_collocations_count"] if collocations else 0
            for row in collocations:
                row.pop("total_collocations_count", None) # Pop the window function count

            # Enhanced response with filter information
            return {
                "total_collocations_count": total_collocations_count, # Use the new name
                "results": collocations
            }

    except asyncpg.exceptions.PostgresError as e:
        logger.error(f"Database error: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {e.detail or e.message}")
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")