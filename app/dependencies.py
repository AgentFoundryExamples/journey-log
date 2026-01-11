# Copyright 2025 John Brosnihan
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""
FastAPI dependency injection providers.

Provides reusable dependency functions for FastAPI routes.
"""

from typing import Annotated
from fastapi import Depends
from google.cloud import firestore

from app.firestore import get_firestore_client


def get_db() -> firestore.Client:
    """
    FastAPI dependency that provides a Firestore client.
    
    This dependency can be injected into any FastAPI route to get
    access to the Firestore client. It uses the lazy-initialized
    singleton from app.firestore.
    
    Returns:
        firestore.Client: The Firestore client instance
        
    Example:
        @app.get("/example")
        async def example_route(db: Annotated[firestore.Client, Depends(get_db)]):
            collection = db.collection('test')
            # ... use the client
    """
    return get_firestore_client()


# Type alias for cleaner dependency injection
FirestoreClient = Annotated[firestore.Client, Depends(get_db)]
