import json
import os
import logging
from typing import List, Set

logger = logging.getLogger(__name__)

class UserManager:
    def __init__(self, admin_ids: List[int], storage_file: str = "authorized_users.json"):
        self.admin_ids = set(admin_ids)
        self.storage_file = storage_file
        self.authorized_users = self._load_users()
        logger.info(f"UserManager initialized with admin IDs: {self.admin_ids}")
        logger.info(f"Loaded authorized users: {self.authorized_users}")

    def _load_users(self) -> Set[int]:
        if os.path.exists(self.storage_file):
            try:
                with open(self.storage_file, 'r') as f:
                    users = set(json.load(f))
                logger.info(f"Loaded users from {self.storage_file}: {users}")
                return users
            except Exception as e:
                logger.error(f"Error loading users from {self.storage_file}: {e}")
                return set()
        logger.info(f"No existing user file found at {self.storage_file}")
        return set()

    def _save_users(self):
        try:
            with open(self.storage_file, 'w') as f:
                json.dump(list(self.authorized_users), f)
            logger.info(f"Saved users to {self.storage_file}: {self.authorized_users}")
        except Exception as e:
            logger.error(f"Error saving users to {self.storage_file}: {e}")

    def is_authorized(self, user_id: int) -> bool:
        is_auth = user_id in self.authorized_users or user_id in self.admin_ids
        logger.info(f"Authorization check for user {user_id}: {is_auth}")
        return is_auth

    def is_admin(self, user_id: int) -> bool:
        is_admin = user_id in self.admin_ids
        logger.info(f"Admin check for user {user_id}: {is_admin}")
        return is_admin

    def add_user(self, admin_id: int, new_user_id: int) -> tuple[bool, str]:
        logger.info(f"Attempting to add user {new_user_id} by admin {admin_id}")
        
        if not self.is_admin(admin_id):
            logger.warning(f"Non-admin user {admin_id} attempted to add user")
            return False, "You are not authorized to add users."
        
        if new_user_id in self.admin_ids:
            logger.warning(f"Attempt to add admin user {new_user_id}")
            return False, "Cannot add admin users."
        
        if new_user_id in self.authorized_users:
            logger.info(f"User {new_user_id} already exists")
            return False, "User is already authorized."
        
        self.authorized_users.add(new_user_id)
        self._save_users()
        logger.info(f"Successfully added user {new_user_id}")
        return True, f"User {new_user_id} has been added successfully."

    def remove_user(self, admin_id: int, user_id: int) -> tuple[bool, str]:
        logger.info(f"Attempting to remove user {user_id} by admin {admin_id}")
        
        if not self.is_admin(admin_id):
            logger.warning(f"Non-admin user {admin_id} attempted to remove user")
            return False, "You are not authorized to remove users."
        
        if user_id in self.admin_ids:
            logger.warning(f"Attempt to remove admin user {user_id}")
            return False, "Cannot remove admin users."
        
        if user_id not in self.authorized_users:
            logger.info(f"User {user_id} not found in authorized users")
            return False, "User is not in the authorized list."
        
        self.authorized_users.remove(user_id)
        self._save_users()
        logger.info(f"Successfully removed user {user_id}")
        return True, f"User {user_id} has been removed successfully."

    def list_users(self, admin_id: int) -> tuple[bool, str]:
        logger.info(f"Attempting to list users by admin {admin_id}")
        
        if not self.is_admin(admin_id):
            logger.warning(f"Non-admin user {admin_id} attempted to list users")
            return False, "You are not authorized to list users."
        
        users_list = "\n".join([f"- {user_id}" for user_id in self.authorized_users])
        response = f"Authorized users:\n{users_list}"
        logger.info(f"Successfully listed users for admin {admin_id}")
        return True, response 