import AppKit
import Foundation
import Vision

struct OCRLine: Codable {
    let text: String
    let confidence: Float
    let boundingBox: [String: Double]
}

guard CommandLine.arguments.count == 2 else {
    FileHandle.standardError.write(Data("Usage: vision_ocr.swift <image>\n".utf8))
    exit(2)
}

let imagePath = CommandLine.arguments[1]
guard
    let image = NSImage(contentsOfFile: imagePath),
    let imageData = image.tiffRepresentation,
    let bitmap = NSBitmapImageRep(data: imageData),
    let cgImage = bitmap.cgImage
else {
    FileHandle.standardError.write(Data("Could not decode image\n".utf8))
    exit(3)
}

let request = VNRecognizeTextRequest()
request.recognitionLevel = .accurate
request.usesLanguageCorrection = true
request.minimumTextHeight = 0.012

do {
    try VNImageRequestHandler(cgImage: cgImage, options: [:]).perform([request])
    let lines = (request.results ?? []).compactMap { observation -> OCRLine? in
        guard let candidate = observation.topCandidates(1).first else { return nil }
        return OCRLine(
            text: candidate.string,
            confidence: candidate.confidence,
            boundingBox: [
                "x": observation.boundingBox.origin.x,
                "y": observation.boundingBox.origin.y,
                "width": observation.boundingBox.size.width,
                "height": observation.boundingBox.size.height,
            ]
        )
    }
    let encoder = JSONEncoder()
    encoder.outputFormatting = [.sortedKeys]
    FileHandle.standardOutput.write(try encoder.encode(lines))
} catch {
    FileHandle.standardError.write(Data("Vision OCR failed: \(error)\n".utf8))
    exit(4)
}
