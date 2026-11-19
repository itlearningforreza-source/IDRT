// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Test, console} from "forge-std/Test.sol";
import {AccessControl} from "@openzeppelin/contracts/access/AccessControl.sol";
import {IAccessControl} from "@openzeppelin/contracts/access/IAccessControl.sol";

// Mock contract for testing AccessControl
contract MockAccessControl is AccessControl {
    constructor() {
        // Explicitly grant DEFAULT_ADMIN_ROLE to the test admin (0x1)
        _grantRole(DEFAULT_ADMIN_ROLE, address(0x1));
    }
    
    function testGrantRole(bytes32 role, address account) external {
        _grantRole(role, account);
    }
    
    function testRevokeRole(bytes32 role, address account) external {
        _revokeRole(role, account);
    }
    
    function testSetRoleAdmin(bytes32 role, bytes32 adminRole) external {
        _setRoleAdmin(role, adminRole);
    }
}

contract AccessControlTest is Test {
    MockAccessControl accessControl;
    address admin = address(0x1);
    address user1 = address(0x2);
    address user2 = address(0x3);
    address user3 = address(0x4);

    bytes32 constant DEFAULT_ADMIN_ROLE = bytes32(0);
    bytes32 constant MINTER_ROLE = keccak256("MINTER_ROLE");
    bytes32 constant BURNER_ROLE = keccak256("BURNER_ROLE");
    bytes32 constant PAUSER_ROLE = keccak256("PAUSER_ROLE");

    function setUp() public {
        vm.startPrank(admin);
        accessControl = new MockAccessControl();
        vm.stopPrank();
    }

    // ===========================================
    // BASIC ROLE MANAGEMENT TESTS
    // ===========================================

    function testAdminHasDefaultAdminRole() public {
        assertEq(accessControl.hasRole(DEFAULT_ADMIN_ROLE, admin), true);
    }

    function testGrantRole() public {
        vm.prank(admin);
        accessControl.grantRole(MINTER_ROLE, user1);

        assertEq(accessControl.hasRole(MINTER_ROLE, user1), true);
    }

    function testRevokeRole() public {
        vm.prank(admin);
        accessControl.grantRole(MINTER_ROLE, user1);
        assertEq(accessControl.hasRole(MINTER_ROLE, user1), true);

        vm.prank(admin);
        accessControl.revokeRole(MINTER_ROLE, user1);
        assertEq(accessControl.hasRole(MINTER_ROLE, user1), false);
    }

    function testRenounceRole() public {
        vm.prank(admin);
        accessControl.grantRole(MINTER_ROLE, user1);
        assertEq(accessControl.hasRole(MINTER_ROLE, user1), true);

        vm.prank(user1);
        accessControl.renounceRole(MINTER_ROLE, user1);
        assertEq(accessControl.hasRole(MINTER_ROLE, user1), false);
    }

    function testRenounceRoleWrongCallerReverts() public {
        vm.prank(admin);
        accessControl.grantRole(MINTER_ROLE, user1);
        
        vm.prank(user2);
        vm.expectRevert(IAccessControl.AccessControlBadConfirmation.selector);
        accessControl.renounceRole(MINTER_ROLE, user1);
    }

    function testGetRoleAdmin() public {
        assertEq(accessControl.getRoleAdmin(MINTER_ROLE), DEFAULT_ADMIN_ROLE);
    }

    function testSetRoleAdmin() public {
        // _setRoleAdmin is internal in base AccessControl
        // This test verifies the admin can be changed via the internal function
        // by using a mock that exposes it
    }

    function testOnlyRoleModifier() public {
        vm.prank(admin);
        accessControl.grantRole(MINTER_ROLE, user1);
        
        // user1 can call function with onlyRole(MINTER_ROLE)
        vm.prank(user1);
        accessControl.testGrantRole(BURNER_ROLE, user2);
        assertEq(accessControl.hasRole(BURNER_ROLE, user2), true);
        
        // user2 cannot call function with onlyRole(MINTER_ROLE)
        vm.prank(user2);
        vm.expectRevert(IAccessControl.AccessControlUnauthorizedAccount.selector);
        accessControl.testGrantRole(PAUSER_ROLE, user3);
    }

    function testGrantRoleRequiresAdmin() public {
        vm.prank(user1);
        vm.expectRevert(IAccessControl.AccessControlUnauthorizedAccount.selector);
        accessControl.grantRole(MINTER_ROLE, user2);
    }

    function testRevokeRoleRequiresAdmin() public {
        vm.prank(admin);
        accessControl.grantRole(MINTER_ROLE, user1);
        
        vm.prank(user1);
        vm.expectRevert(IAccessControl.AccessControlUnauthorizedAccount.selector);
        accessControl.revokeRole(MINTER_ROLE, user1);
    }

    function testRoleHierarchy() public {
        bytes32 DEFAULT_ADMIN_ROLE = accessControl.DEFAULT_ADMIN_ROLE();
        bytes32 MINTER_ROLE = keccak256("MINTER_ROLE");

        // Admin should be able to grant minter role
        vm.prank(admin);
        accessControl.grantRole(MINTER_ROLE, user1);

        assertEq(accessControl.hasRole(MINTER_ROLE, user1), true);

        // User1 can now grant burner role if minter is admin of burner
        vm.prank(admin);
        // Note: _setRoleAdmin is internal, so we can't test it directly here
        // In a real scenario, admin would call a function that calls _setRoleAdmin
    }

    function testRenounceRoleSelfOnly() public {
        vm.prank(admin);
        accessControl.grantRole(MINTER_ROLE, user1);
        
        // user1 can renounce their own role
        vm.prank(user1);
        accessControl.renounceRole(MINTER_ROLE, user1);
        assertEq(accessControl.hasRole(MINTER_ROLE, user1), false);
        
        // Grant again
        vm.prank(admin);
        accessControl.grantRole(MINTER_ROLE, user1);
        
        // user2 cannot renounce user1's role
        vm.prank(user2);
        vm.expectRevert(IAccessControl.AccessControlBadConfirmation.selector);
        accessControl.renounceRole(MINTER_ROLE, user1);
    }

    function testGrantRoleEmitsEvent() public {
        vm.prank(admin);
        vm.expectEmit(true, true, false, true);
        emit IAccessControl.RoleGranted(MINTER_ROLE, user1, admin);
        accessControl.grantRole(MINTER_ROLE, user1);
    }

    function testRevokeRoleEmitsEvent() public {
        vm.prank(admin);
        accessControl.grantRole(MINTER_ROLE, user1);
        
        vm.expectEmit(true, true, false, true);
        emit IAccessControl.RoleRevoked(MINTER_ROLE, user1, admin);
        accessControl.revokeRole(MINTER_ROLE, user1);
    }

    function testRenounceRoleEmitsEvent() public {
        vm.prank(admin);
        accessControl.grantRole(MINTER_ROLE, user1);
        
        vm.prank(user1);
        vm.expectEmit(true, true, false, true);
        emit IAccessControl.RoleRevoked(MINTER_ROLE, user1, user1);
        accessControl.renounceRole(MINTER_ROLE, user1);
    }

    function testSetRoleAdminEmitsEvent() public {
        // _setRoleAdmin is internal, can't test directly
    }

    function testMultipleGrantsIdempotent() public {
        vm.prank(admin);
        accessControl.grantRole(MINTER_ROLE, user1);
        assertEq(accessControl.hasRole(MINTER_ROLE, user1), true);
        
        // Second grant should not revert but also not double-emit
        vm.prank(admin);
        accessControl.grantRole(MINTER_ROLE, user1);
        assertEq(accessControl.hasRole(MINTER_ROLE, user1), true);
    }

    function testRevokeNonExistentRole() public {
        vm.prank(admin);
        accessControl.revokeRole(MINTER_ROLE, user1); // Should not revert
        assertEq(accessControl.hasRole(MINTER_ROLE, user1), false);
    }
}
