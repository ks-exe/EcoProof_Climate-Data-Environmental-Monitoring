// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;
import {BatchRegistry} from "../BatchRegistry.sol";

contract OtherCaller {
    function attempt(BatchRegistry registry) external returns (bool, bytes memory) {
        return address(registry).call(abi.encodeCall(registry.anchor, (bytes32(uint256(1)), bytes32(uint256(2)), 1, 2, 1)));
    }
}

contract BatchRegistryTest {
    BatchRegistry registry;
    bytes32 constant KEY = keccak256("synthetic-contract-test");
    bytes32 constant ROOT = sha256("synthetic-root");

    function setUp() public { registry = new BatchRegistry(); }

    function assertRevert(bytes32 key, bytes32 root, uint64 ws, uint64 we, uint32 count, string memory reason) internal {
        (bool ok, bytes memory data) = address(registry).call(abi.encodeCall(registry.anchor, (key, root, ws, we, count)));
        require(!ok, "expected revert");
        require(keccak256(data) == keccak256(abi.encodeWithSignature("Error(string)", reason)), "wrong revert reason");
    }

    function testOwnerAndStoredFields() public {
        require(registry.owner() == address(this), "wrong owner");
        registry.anchor(KEY, ROOT, 100, 3700, 3);
        (bytes32 root, uint64 ws, uint64 we, uint32 count, uint64 at) = registry.batches(KEY);
        require(root == ROOT && ws == 100 && we == 3700 && count == 3, "wrong fields");
        require(at == block.timestamp && at > 0, "wrong anchored timestamp");
    }

    function testDuplicateAnchorRevertsAndPreservesOriginal() public {
        registry.anchor(KEY, ROOT, 100, 3700, 3);
        assertRevert(KEY, bytes32(uint256(9)), 200, 3800, 9, "already anchored");
        (bytes32 root, uint64 ws, uint64 we, uint32 count,) = registry.batches(KEY);
        require(root == ROOT && ws == 100 && we == 3700 && count == 3, "overwritten");
    }

    function testOnlyOwnerCanAnchor() public {
        (bool ok, bytes memory data) = (new OtherCaller()).attempt(registry);
        require(!ok, "non-owner allowed");
        require(keccak256(data) == keccak256(abi.encodeWithSignature("Error(string)", "not owner")), "wrong reason");
    }

    function testEmptyKeyRejected() public { assertRevert(bytes32(0), ROOT, 1, 2, 1, "empty key"); }
    function testEmptyRootRejected() public { assertRevert(KEY, bytes32(0), 1, 2, 1, "empty root"); }
    function testEmptyBatchRejected() public { assertRevert(KEY, ROOT, 1, 2, 0, "empty batch"); }
    function testInvalidWindowsRejected() public {
        assertRevert(KEY, ROOT, 2, 2, 1, "invalid window");
        assertRevert(KEY, ROOT, 3, 2, 1, "invalid window");
    }

    function testDifferentKeysAreIndependent() public {
        registry.anchor(KEY, ROOT, 1, 2, 1);
        registry.anchor(bytes32(uint256(7)), bytes32(uint256(8)), 2, 3, 2);
        (bytes32 root,,,,) = registry.batches(KEY);
        require(root == ROOT, "changed previous batch");
    }

    function testFuzzRoundTrip(bytes32 key, bytes32 root, uint64 ws, uint32 count) public {
        if (key == 0) key = bytes32(uint256(1));
        if (root == 0) root = bytes32(uint256(1));
        if (count == 0) count = 1;
        ws = ws % (type(uint64).max - 3600);
        registry.anchor(key, root, ws, ws + 3600, count);
        (bytes32 actual, uint64 start, uint64 end, uint32 size,) = registry.batches(key);
        require(actual == root && start == ws && end == ws + 3600 && size == count, "fuzz mismatch");
    }
}
