"""
Load REIT companies into the database
"""
import requests
from bs4 import BeautifulSoup
from models import init_db, get_session, Company
from datetime import datetime
import time

# Your list of REIT tickers
REIT_TICKERS = [
    'AAT', 'ABR', 'ACR', 'ADC', 'AHH', 'AHR', 'AHT', 'AKR', 'ALEX', 'ALX',
    'AMT', 'AOMR', 'APLE', 'ARE', 'ARI', 'ARR', 'AVB', 'BDN', 'BFS', 'BHM',
    'BHR', 'BNL', 'BRSP', 'BRX', 'BXMT', 'BXP', 'CBL', 'CCI', 'CDP', 'CLDT',
    'CMTG', 'COLD', 'CPT', 'CSR', 'CTO', 'CTRE', 'CUBE', 'CURB', 'CUZ', 'DEA',
    'DLR', 'DOC', 'DRH', 'DX', 'EGP', 'ELME', 'ELS', 'EPR', 'EPRT', 'EQR',
    'ESRT', 'ESS', 'EXR', 'FBRT', 'FCPT', 'FR', 'FRT', 'FSP', 'FVR', 'GNL',
    'GTY', 'HHH', 'HIW', 'HPP', 'HR', 'INN', 'INVH', 'IRM', 'IVT', 'JBGS',
    'KIM', 'KRC', 'KRG', 'LADR', 'LTC', 'LXP', 'MAA', 'MAC', 'MFA', 'MPW',
    'MRP', 'NHI', 'NNN', 'NREF', 'NSA', 'NTST', 'NXDT', 'NXRT', 'O', 'OHI',
    'OLP', 'ONL', 'OUT', 'PDM', 'PEB', 'PGRE', 'PINE', 'PK', 'PKST', 'PLD',
    'PLYM', 'PMT', 'PSA', 'PSTL', 'RC', 'RHP', 'RLJ', 'RPT', 'RYN', 'SAFE',
    'SHO', 'SILA', 'SKT', 'SLG', 'SMA', 'SPG', 'STAG', 'STWD', 'SUI', 'TRNO',
    'TRTX', 'UDR', 'UE', 'UMH', 'VICI', 'VNO', 'VRE', 'VTR', 'WELL', 'WPC',
    'WSR', 'WY', 'XHR'
]


def find_ir_url(ticker, company_name=None):
    """
    Attempt to find the investor relations URL for a REIT
    Uses common patterns and search
    """
    # Common IR URL patterns
    common_patterns = [
        f"https://investors.{ticker.lower()}.com",
        f"https://ir.{ticker.lower()}.com",
        f"https://investor.{ticker.lower()}.com",
        f"https://www.{ticker.lower()}.com/investors",
        f"https://www.{ticker.lower()}.com/investor-relations",
    ]
    
    # Try common patterns first
    for url in common_patterns:
        try:
            response = requests.head(url, timeout=5, allow_redirects=True)
            if response.status_code == 200:
                return url
        except:
            continue
    
    # If no common pattern works, return None (will need manual entry)
    return None


def get_company_name_from_ticker(ticker):
    """
    Try to get company name from public sources
    This is a simple implementation - you may want to enhance it
    """
    try:
        # Try Yahoo Finance
        url = f"https://finance.yahoo.com/quote/{ticker}"
        response = requests.get(url, timeout=10, headers={
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        })
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.content, 'html.parser')
            # Yahoo Finance has the company name in the h1 tag
            h1 = soup.find('h1')
            if h1:
                name = h1.text.strip()
                # Remove ticker in parentheses
                if '(' in name:
                    name = name.split('(')[0].strip()
                return name
    except:
        pass
    
    return None


def load_reits_to_database(batch_size=10):
    """
    Load REIT tickers into the database
    """
    engine = init_db()
    session = get_session(engine)
    
    print(f"Loading {len(REIT_TICKERS)} REITs into database...")
    
    added = 0
    skipped = 0
    
    for i, ticker in enumerate(REIT_TICKERS):
        # Check if already exists
        existing = session.query(Company).filter_by(ticker=ticker).first()
        if existing:
            print(f"[{i+1}/{len(REIT_TICKERS)}] {ticker} - Already in database")
            skipped += 1
            continue
        
        print(f"[{i+1}/{len(REIT_TICKERS)}] Processing {ticker}...")
        
        # Get company name
        company_name = get_company_name_from_ticker(ticker)
        
        # Try to find IR URL
        ir_url = find_ir_url(ticker, company_name)
        
        # Create company record
        company = Company(
            ticker=ticker,
            name=company_name or f"{ticker} (Name TBD)",
            ir_url=ir_url,
            active=True
        )
        
        session.add(company)
        added += 1
        
        print(f"  → Name: {company.name}")
        print(f"  → IR URL: {ir_url or 'Not found - needs manual entry'}")
        
        # Commit in batches to avoid memory issues
        if (i + 1) % batch_size == 0:
            session.commit()
            print(f"\n--- Committed batch of {batch_size} ---\n")
            time.sleep(1)  # Be nice to servers
    
    # Final commit
    session.commit()
    
    print(f"\n{'='*60}")
    print(f"REIT loading complete!")
    print(f"Added: {added}")
    print(f"Skipped (already existed): {skipped}")
    print(f"Total in database: {session.query(Company).count()}")
    print(f"{'='*60}")
    
    # Show companies that need manual IR URL entry
    needs_ir = session.query(Company).filter(Company.ir_url.is_(None)).all()
    if needs_ir:
        print(f"\n{len(needs_ir)} companies need IR URLs manually entered:")
        for company in needs_ir[:10]:  # Show first 10
            print(f"  - {company.ticker}: {company.name}")
        if len(needs_ir) > 10:
            print(f"  ... and {len(needs_ir) - 10} more")
    
    session.close()
    return added, skipped


if __name__ == "__main__":
    load_reits_to_database()
