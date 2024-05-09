"use strict";


var gulp = require('gulp');
var gutil = require('gulp-util');
var uglify = require('gulp-uglify');
var concat = require('gulp-concat');
var rename = require('gulp-rename');
var merge = require('merge-stream');
var shell = require('gulp-shell');
var merge = require('merge-stream');
var child_process = require('child_process');
var exec = require('child_process').exec;
var execSync = require('child_process').execSync;
var fs = require('fs');
var path = require('path');
var del = require('del');
var _ = require('underscore');


// Script Inital Working Directory
var sonador_rootdir = process.cwd();


// Project Root Folders
var sonador_styles = './styles/';
var sonador_jslib = './sonador/jslib/';
var sonador_static = './sonador/static/';
var sonador_static_css = sonador_static+'css/';
var sonador_static_js = sonador_static+'js/';


// Guru/Base Dependencies
var guru_jslib = './lib/guru/jslib/';
var guru_static = './lib/guru/static/';
var guru_static_css = guru_static+'css/';
var guru_static_js = guru_static+'js/';
var guru_jslib_mlightbox = guru_jslib+'mlightbox/';


// Visionaire and OHIF
var visionaire_jslib = './apps/visionaire/jslib/';
var visionaire_jslib_ohif = visionaire_jslib+'ohif/';
var visionaire_static = './apps/visionaire/static/';
var visionaire_static_css = visionaire_static+'css/';
var visionaire_static_js = visionaire_static+'js/';

// OHIF Extensions
var visionaire_jslib_extensions = visionaire_jslib_ohif+'extensions/';
var visionaire_jslib_cornerstone = visionaire_jslib_extensions+'cornerstone/';
var visionaire_jslib_vtk = visionaire_jslib_extensions+'vtk/';
var visionaire_jslib_microscopy = visionaire_jslib_extensions+'dicom-microscopy/';
var visionaire_jslib_segmentation = visionaire_jslib_extensions+'dicom-segmentation/';
var visionaire_jslib_html = visionaire_jslib_extensions+'dicom-html/';
var visionaire_jslib_p10 = visionaire_jslib_extensions+'dicom-p10-downloader/';
var visionaire_jslib_pdf = visionaire_jslib_extensions+'dicom-pdf/';
var visionaire_jslib_rt = visionaire_jslib_extensions+'dicom-rt/';
var visionaire_jslib_dcmtag = visionaire_jslib_extensions+'dicom-tag-browser/';
var visionaire_jslib_tracker = visionaire_jslib_extensions+'lesion-tracker/';


// Content Widgets
var content_jslib = './lib/content/jslib/';
var content_jslib_ace = content_jslib+'ace/';
var content_static = './lib/content/static/';
var content_static_js = content_static+'js/';
var content_static_css = content_static+'css/';



// Build and compile standalone OHIF components

function jsBuildOHIFViewer(done){
	console.log('Compile and copy OHIF: ', visionaire_jslib_ohif);

	var visionaire_jslib_ohif_node_deps = visionaire_jslib_ohif+'node_modules/';
	var ohif_deps, build_ohif;

	try {

		// Determine if necessary dependencies are installed
		ohif_deps = fs.lstatSync(visionaire_jslib_ohif_node_deps);
		build_ohif = true;

	} catch(err) {

		// Dependencies not yet installed, change to Foundation directory and install
		try {
			console.info('Dependencies for OHIF have not yet been installed. Install to: ',
				visionaire_jslib_ohif_node_deps);
			process.chdir(visionaire_jslib_ohif);
			execSync('yarn config set workspaces-experimental true')
			execSync('yarn install')
			console.info('OHIF dependencies installed successfully');
			build_ohif = true;
			process.chdir(sonador_rootdir);

		} catch(err) {

			// Indicate that an error occurred, stop build
			console.error('Error occurrered while trying to install node dependencies: ', err);
			process.chdir(sonador_rootdir);
			return done();

		}
	} finally {

		if (build_ohif) { 
			try {
				process.chdir(visionaire_jslib_ohif);

				// Execute Foundation build script
				console.info('Build OHIF with default options');
				execSync('yarn build:package', { maxBuffer: 209715200 });
				console.info('Build of OHIF completed successfully');

				process.chdir(sonador_rootdir);
			} catch(err){

				// Indicate that an error occurred, stop build
				console.error('Error while trying to build OHIF: ', err);
				process.chdir(sonador_rootdir);

				return done();
			}
		}
	}

	return done();
}


// Deploy static assets
var ohif_jsfolders = {
	viewer: {
		src: visionaire_jslib_ohif, 
		build: visionaire_jslib_ohif+'platform/viewer/dist/*',
		dst: visionaire_static_js+'ohif/'
	},
}


function deployOHIF(done) {
	console.info('Deploy compiled JavaScript OHIF assets to static folders');
	var tasks = _.keys(ohif_jsfolders).map(function(f) {
		console.info('Copy files for', f, 'from', ohif_jsfolders[f].build, 'to', ohif_jsfolders[f].dst);
		return gulp.src(ohif_jsfolders[f].build).pipe(gulp.dest(ohif_jsfolders[f].dst));
	});

	return merge(tasks);
}


function jsBuildAce(done) {
	console.log('Compile and minify ACE code editor: ', content_jslib_ace);
	var content_jslib_ace_node_deps = content_jslib_ace+'node_modules/';
	var ace_deps, build_ace;

	try{

		//
		ace_deps = fs.lstatSync(content_jslib_ace_node_deps);
		build_ace = true;

	} catch (err) {

		// Dependencies not yet installed, cahnge to jslib directory and install
		try {

			console.info('Dependencies for ACE JS have not yet been installed. Install to ',
				content_jslib_ace_node_deps);
			process.chdir(content_jslib_ace);
			execSync('npm install');
			console.info('ACE JS depdencies installed succesfully');
			build_ace = true;
			process.chdir(sonador_rootdir);
		} catch (err) {

			// Indicate that an error occurred, stop build
			console.log('Error while trying to install node dependencies: ', err);
			process.chdir(sonador_rootdir);
			done();
		}
	} finally {

		if (build_ace) {
			try {
				process.chdir(content_jslib_ace);

				// Execue ACE build script
				console.log('Build ACE JS with default options');
				execSync('node ./Makefile.dryice.js');
				console.info('Build of ACE JS completed succesfully');

				process.chdir(sonador_rootdir);
			} catch (err) {

				// Indicate that an error occurred, stop build
				console.log('Error while trying to build ACE JS: ', err);
				process.chdir(sonador_rootdir);
				done();
			}
		} else { done(); }
	}

	return gulp.src(content_jslib_ace+'build/src/**/*.js')
		.pipe(gulp.dest(content_static_js+'ace/'));
}


function jsBuildMagnificLightbox(done) {

	console.log('Compile and minify Magnific Popup to static folder: ', guru_jslib_mlightbox);
	var guru_jslib_mlightbox_node_deps = guru_jslib_mlightbox+'node_modules/';
	var mlightbox_deps, build_mlightbox;

	try {
		// Determine if necessary dependencies are installed
		mlightbox_deps = fs.lstatSync(guru_jslib_mlightbox_node_deps);
		build_mlightbox = true;
	
	} catch(err) {

		// Dependencies not yet installed, change to jslib directory and install
		try {

			console.info('Dependencies for Magnific Popup have not yet been installed. Install to ', 
				guru_jslib_mlightbox_node_deps);
			process.chdir(guru_jslib_mlightbox);
			execSync('npm install');
			console.info('Magnific Popup dependencies installed successfully');
			build_mlightbox = true;
			process.chdir(sonador_rootdir);

		} catch (err) {

			// Indicate that an error occurred, stop build
			console.log('Error while trying to install node dependencies: ', err);
			process.chdir(sonador_rootdir);
			done();
		}
	
	} finally {

		if (build_mlightbox) {
			try {
				process.chdir(guru_jslib_mlightbox);

				// Execute Highlight.js build script
				console.info('Build Magnific Popup with default options');
				execSync('grunt mfpbuild');
				console.info('Build of Magnific Popup completed succesfully');

				process.chdir(sonador_rootdir);
			} catch (err) {

				// Indicate that an error occurred, stop build
				console.log('Error while trying to build Magnific Popup: ', err);
				process.chdir(sonador_rootdir);
				done();
			}
		} else { done(); }
	}

	return gulp.src(guru_jslib_mlightbox+'dist/*.js').pipe(gulp.dest(guru_static_js+'mlightbox/'));

}


// Compile 
const js = gulp.series(jsBuildOHIFViewer, deployOHIF, jsBuildAce, jsBuildMagnificLightbox);
const jsOHIF = gulp.series(jsBuildOHIFViewer, deployOHIF)


// Gulp Tasks
exports.jsBuildOHIFViewer = jsBuildOHIFViewer;
exports.deployOHIF = deployOHIF;
exports.jsBuildAce = jsBuildAce;
exports.jsBuildMagnificLightbox = jsBuildMagnificLightbox;
exports.jsOHIF = jsOHIF;
exports.js = js;
