// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @notice Write-once commitments. Inclusion does not establish sensor accuracy.
contract BatchRegistry {
    address public immutable owner;
    struct Batch {
        bytes32 root;
        uint64 windowStart;
        uint64 windowEnd;
        uint32 count;
        uint64 anchoredAt;
    }
    mapping(bytes32 => Batch) public batches;
    event BatchAnchored(bytes32 indexed batchKey, bytes32 root, uint32 count);

    constructor() { owner = msg.sender; }

    function anchor(bytes32 key, bytes32 root, uint64 ws, uint64 we, uint32 count) external {
        require(msg.sender == owner, "not owner");
        require(batches[key].anchoredAt == 0, "already anchored");
        require(key != bytes32(0), "empty key");
        require(root != bytes32(0), "empty root");
        require(ws < we, "invalid window");
        require(count > 0, "empty batch");
        batches[key] = Batch(root, ws, we, count, uint64(block.timestamp));
        emit BatchAnchored(key, root, count);
    }
}
